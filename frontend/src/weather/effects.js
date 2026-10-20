// 每種場景要顯示哪些特效、強度多少。所有數值集中在這裡，調整外觀只改這個檔案。
//
// 回傳的欄位：
//   skyTop / skyBottom  背景漸層（null 代表沿用網頁原本的背景色）
//   tone       天空的明暗：light 用深色文字，dark 用淺色文字，null 跟著系統的深淺色模式
//   sun        陽光、光束、光暈（0–1，只在白天）
//   moon       月亮（0–1，只在晚上）
//   stars      星星（0–1，只在晚上）
//   clouds     雲層的不透明度（0–1）
//   cloudShade 雲的顏色：light 白雲、dark 烏雲
//   fog        霧氣（0–1）
//   precipitation  { type: 'rain' | 'snow', density, speed, length, opacity, wind }；沒有降水是 null
//   lightning  是否偶爾閃電

const SKY = {
  clear: { day: ['#2c69ad', '#b3d7f3'], night: ['#0b1531', '#25395f'] },
  cloudy: { day: ['#476887', '#c6d5e3'], night: ['#121b30', '#2d3b56'] },
  overcast: { day: ['#58626c', '#b8bfc7'], night: ['#181d26', '#323843'] },
  drizzle: { day: ['#4a5d6f', '#aab7c3'], night: ['#121a26', '#2b3543'] },
  rain: { day: ['#4b5d6e', '#93a2af'], night: ['#0f1621', '#27313e'] },
  'heavy-rain': { day: ['#36434f', '#6f7c88'], night: ['#0b1018', '#202833'] },
  storm: { day: ['#262b38', '#4f5566'], night: ['#090b12', '#1c202c'] },
  snow: { day: ['#435d79', '#e6edf5'], night: ['#1c273a', '#45556d'] },
  fog: { day: ['#59646e', '#d6dbe0'], night: ['#20252e', '#3c434e'] },
  unknown: { day: ['#44607a', '#c8d4df'], night: ['#141c2c', '#2f3a4c'] },
}

const NONE = {
  sun: 0,
  moon: 0,
  stars: 0,
  clouds: 0,
  cloudShade: 'light',
  fog: 0,
  precipitation: null,
  lightning: false,
}

function rain({ density, speed, length, opacity, wind }) {
  return { type: 'rain', density, speed, length, opacity, wind }
}

/** 依場景計算特效設定。純函式，同樣的場景一定得到同樣的結果。 */
export function getEffects(scene) {
  const { kind, intensity = 0, cloudCover = 0, night = false } = scene ?? {}
  if (!SKY[kind]) {
    return { ...NONE, skyTop: null, skyBottom: null, tone: null }
  }

  const [skyTop, skyBottom] = SKY[kind][night ? 'night' : 'day']
  const effects = { ...NONE, skyTop, skyBottom, tone: 'dark', clouds: cloudCover }

  switch (kind) {
    case 'clear':
      effects.sun = night ? 0 : 1
      effects.moon = night ? 1 : 0
      effects.stars = night ? 1 : 0
      break
    case 'cloudy':
      effects.sun = night ? 0 : 0.45
      effects.moon = night ? 0.45 : 0
      effects.stars = night ? 0.3 : 0
      break
    case 'overcast':
      effects.fog = 0.15
      break
    case 'drizzle':
      effects.fog = 0.2
      effects.precipitation = rain({
        density: 0.15 + 0.25 * intensity,
        speed: 0.55,
        length: 0.45,
        opacity: 0.35,
        wind: 0.05,
      })
      break
    case 'rain':
      effects.fog = 0.2
      effects.precipitation = rain({
        density: 0.35 + 0.4 * intensity,
        speed: 0.8,
        length: 0.75,
        opacity: 0.45,
        wind: 0.12,
      })
      break
    case 'heavy-rain':
      effects.cloudShade = 'dark'
      effects.fog = 0.3
      effects.precipitation = rain({ density: 1, speed: 1, length: 1, opacity: 0.55, wind: 0.2 })
      break
    case 'storm':
      effects.cloudShade = 'dark'
      effects.fog = 0.2
      effects.lightning = true
      effects.precipitation = rain({
        density: 0.7 + 0.3 * intensity,
        speed: 1,
        length: 1,
        opacity: 0.5,
        wind: 0.25,
      })
      break
    case 'snow':
      effects.fog = 0.15
      effects.precipitation = { type: 'snow', density: 0.25 + 0.75 * intensity, speed: 0.5, opacity: 0.85 }
      break
    case 'fog':
      effects.fog = 0.45 + 0.4 * intensity
      effects.sun = night ? 0 : 0.2
      break
    default:
      break
  }
  return effects
}

/** 給版面使用：天空亮時用深色文字，暗時用淺色文字；沒有天空時跟著系統主題。 */
export function skyTone(scene) {
  return getEffects(scene).tone
}
