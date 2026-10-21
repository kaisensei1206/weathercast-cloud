// 用一個 Canvas 畫雨和雪，疊在背景地圖上。
//
// - 引擎只在元件掛上時建立一次；換天氣只呼叫 setConfig，不會重建 Canvas 或重新註冊事件。
// - 粒子數量依螢幕大小和 CPU 核心數調整，手機和低階裝置畫得比較少。
// - 每一層的雨滴合併成一條路徑一次畫完，不會每滴雨呼叫一次 stroke。
// - 分頁切到背景時暫停；偏好減少動態效果時只畫一張靜態畫面。

const MAX_RAIN = 260
const MAX_SNOW = 160
const REFERENCE_AREA = 1280 * 800

// 三層景深：越遠越細、越慢、越淡
const RAIN_LAYERS = [
  { share: 0.45, width: 0.8, alpha: 0.45, speed: 0.75, length: 0.7 },
  { share: 0.35, width: 1.1, alpha: 0.7, speed: 0.9, length: 0.85 },
  { share: 0.2, width: 1.5, alpha: 1, speed: 1.1, length: 1 },
]
const SNOW_LAYERS = [
  { share: 0.5, radius: [1, 2], alpha: 0.55, speed: 0.6 },
  { share: 0.35, radius: [2, 3.2], alpha: 0.8, speed: 0.85 },
  { share: 0.15, radius: [3.2, 4.5], alpha: 1, speed: 1.1 },
]

/**
 * 粒子數量的倍率（0.25–1）：螢幕越小、CPU 核心越少，倍率越低。
 * 1280×800、8 核以上是 1。
 */
export function particleBudget({ width, height, cores = 8 }) {
  const areaFactor = Math.min(1, Math.max(0.35, (width * height) / REFERENCE_AREA))
  const cpuFactor = cores <= 2 ? 0.5 : cores <= 4 ? 0.75 : 1
  return Math.max(0.25, areaFactor * cpuFactor)
}

/** 依降水設定和倍率算出目標粒子數。 */
export function targetCounts(config, budget) {
  const precipitation = config?.precipitation
  const rainCount =
    precipitation?.type === 'rain' ? Math.round(MAX_RAIN * precipitation.density * budget) : 0
  const snowCount =
    precipitation?.type === 'snow' ? Math.round(MAX_SNOW * precipitation.density * budget) : 0
  return { rain: rainCount, snow: snowCount }
}

function pickLayer(layers) {
  let r = Math.random()
  for (let i = 0; i < layers.length; i++) {
    r -= layers[i].share
    if (r <= 0) return i
  }
  return layers.length - 1
}

const random = (min, max) => min + Math.random() * (max - min)

const NOOP_ENGINE = Object.freeze({
  setConfig() {},
  setReducedMotion() {},
  destroy() {},
})

/**
 * @param {HTMLCanvasElement} canvas
 * @param {{ reducedMotion?: boolean }} options
 */
export function createParticleEngine(canvas, { reducedMotion = false } = {}) {
  const ctx = canvas?.getContext?.('2d')
  if (!ctx) return NOOP_ENGINE // 不支援 Canvas（例如測試環境）時什麼都不做

  const cores = typeof navigator !== 'undefined' ? navigator.hardwareConcurrency || 4 : 4
  let width = 0
  let height = 0
  let budget = 1
  let config = null
  let targets = { rain: 0, snow: 0 }
  let reduced = reducedMotion
  let frame = 0
  let lastTime = 0
  let elapsed = 0
  const rain = []
  const snow = []

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, cores <= 4 ? 1.5 : 2)
    width = window.innerWidth
    height = window.innerHeight
    canvas.width = Math.round(width * dpr)
    canvas.height = Math.round(height * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    budget = particleBudget({ width, height, cores })
    targets = targetCounts(config, budget)
    fill(true)
    if (reduced) drawStill()
  }

  function newRainDrop(anywhere) {
    const layer = pickLayer(RAIN_LAYERS)
    return {
      layer,
      x: random(-0.1 * width, 1.1 * width),
      y: anywhere ? random(-height, height) : random(-0.3 * height, -10),
      speed: random(0.85, 1.15),
      length: random(0.7, 1.3),
    }
  }

  function newSnowflake(anywhere) {
    const layer = pickLayer(SNOW_LAYERS)
    const [rMin, rMax] = SNOW_LAYERS[layer].radius
    return {
      layer,
      x: random(0, width),
      y: anywhere ? random(-height, height) : random(-0.2 * height, -5),
      r: random(rMin, rMax),
      speed: random(0.8, 1.2),
      sway: random(10, 28),
      phase: random(0, Math.PI * 2),
      swaySpeed: random(0.4, 0.9),
    }
  }

  // 補足不夠的粒子；多出來的不立刻刪掉，等它們落出畫面再回收，避免畫面突然變空
  function fill(anywhere) {
    while (rain.length < targets.rain) rain.push(newRainDrop(anywhere))
    while (snow.length < targets.snow) snow.push(newSnowflake(anywhere))
  }

  function updateRain(dt) {
    const p = config.precipitation
    const fall = 900 * p.speed
    const drift = fall * p.wind
    for (let i = rain.length - 1; i >= 0; i--) {
      const drop = rain[i]
      const layer = RAIN_LAYERS[drop.layer]
      drop.y += fall * layer.speed * drop.speed * dt
      drop.x += drift * layer.speed * dt
      if (drop.y > height + 40 || drop.x > width * 1.15) {
        if (i >= targets.rain) rain.splice(i, 1)
        else rain[i] = newRainDrop(false)
      }
    }
  }

  function updateSnow(dt) {
    const fall = 70 * config.precipitation.speed
    for (let i = snow.length - 1; i >= 0; i--) {
      const flake = snow[i]
      flake.y += fall * SNOW_LAYERS[flake.layer].speed * flake.speed * dt
      if (flake.y > height + 10) {
        if (i >= targets.snow) snow.splice(i, 1)
        else snow[i] = newSnowflake(false)
      }
    }
  }

  function drawRain() {
    const p = config.precipitation
    const baseLength = 26 * p.length
    for (let l = 0; l < RAIN_LAYERS.length; l++) {
      const layer = RAIN_LAYERS[l]
      ctx.beginPath()
      for (const drop of rain) {
        if (drop.layer !== l) continue
        const len = baseLength * layer.length * drop.length
        ctx.moveTo(drop.x, drop.y)
        ctx.lineTo(drop.x - len * p.wind, drop.y - len)
      }
      ctx.lineWidth = layer.width
      ctx.strokeStyle = `rgba(70, 110, 160, ${(p.opacity * layer.alpha).toFixed(3)})`
      ctx.stroke()
    }
  }

  function drawSnow() {
    const opacity = config.precipitation.opacity
    for (let l = 0; l < SNOW_LAYERS.length; l++) {
      ctx.beginPath()
      for (const flake of snow) {
        if (flake.layer !== l) continue
        const x = flake.x + Math.sin(elapsed * flake.swaySpeed + flake.phase) * flake.sway
        ctx.moveTo(x + flake.r, flake.y)
        ctx.arc(x, flake.y, flake.r, 0, Math.PI * 2)
      }
      const alpha = opacity * SNOW_LAYERS[l].alpha
      ctx.fillStyle = `rgba(255, 255, 255, ${alpha.toFixed(3)})`
      ctx.fill()
      // 淡淡的深色外框：地圖是淺灰色，只有白色的雪會看不清楚
      ctx.lineWidth = 0.75
      ctx.strokeStyle = `rgba(60, 80, 110, ${(alpha * 0.45).toFixed(3)})`
      ctx.stroke()
    }
  }

  function draw() {
    ctx.clearRect(0, 0, width, height)
    if (!config) return
    if (rain.length && config.precipitation?.type === 'rain') drawRain()
    if (snow.length && config.precipitation?.type === 'snow') drawSnow()
  }

  function drawStill() {
    // 減少動態效果：不動畫，只畫一張靜態的雨或雪，仍然看得出天氣
    rain.length = 0
    snow.length = 0
    fill(true)
    draw()
  }

  function tick(now) {
    frame = 0
    const dt = Math.min(0.05, (now - (lastTime || now)) / 1000) // 分頁切回來時不要一次跳太多
    lastTime = now
    elapsed += dt
    if (config?.precipitation?.type === 'rain') updateRain(dt)
    else rain.length = 0
    if (config?.precipitation?.type === 'snow') updateSnow(dt)
    else snow.length = 0
    fill(false)
    draw()
    if (isAnimating()) start()
  }

  function isAnimating() {
    return !reduced && !document.hidden && (rain.length > 0 || snow.length > 0)
  }

  function start() {
    if (!frame) frame = requestAnimationFrame(tick)
  }

  function stop() {
    if (frame) cancelAnimationFrame(frame)
    frame = 0
    lastTime = 0
  }

  function refresh() {
    targets = targetCounts(config, budget)
    if (reduced) {
      stop()
      drawStill()
      return
    }
    fill(false)
    if (isAnimating()) start()
    else {
      stop()
      draw() // 清掉上一個天氣留下的畫面
    }
  }

  function onVisibilityChange() {
    if (document.hidden) stop()
    else refresh()
  }

  let resizeFrame = 0
  function onResize() {
    if (resizeFrame) return
    resizeFrame = requestAnimationFrame(() => {
      resizeFrame = 0
      resize()
    })
  }

  window.addEventListener('resize', onResize)
  document.addEventListener('visibilitychange', onVisibilityChange)
  resize()

  return {
    /** @param {{ precipitation: object | null }} next */
    setConfig(next) {
      const typeChanged = next?.precipitation?.type !== config?.precipitation?.type
      config = next
      if (typeChanged) {
        rain.length = 0
        snow.length = 0
        targets = targetCounts(config, budget)
        fill(true) // 換成另一種降水時直接鋪滿畫面，不要等雨從上面慢慢落下
      }
      refresh()
    },
    setReducedMotion(value) {
      reduced = value
      refresh()
    },
    destroy() {
      stop()
      if (resizeFrame) cancelAnimationFrame(resizeFrame)
      window.removeEventListener('resize', onResize)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      ctx.clearRect(0, 0, width, height)
    },
  }
}
