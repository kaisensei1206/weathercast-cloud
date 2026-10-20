import { useEffect, useMemo, useRef } from 'react'
import { getEffects } from '../weather/effects.js'
import { createParticleEngine } from '../weather/particles.js'
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion.js'

// 閃電間隔（毫秒）：每次隨機，避免規律閃爍
const LIGHTNING_MIN_MS = 7000
const LIGHTNING_MAX_MS = 15000

/**
 * 整個畫面後方的天氣背景。純裝飾：pointer-events: none、aria-hidden，不影響操作與閱讀。
 *
 * - 天空、太陽、月亮、雲、霧用 CSS（漸層加 transform 動畫，交給 GPU）。
 * - 雨、雪、星星用一個 Canvas，引擎只建立一次，換天氣只更新設定。
 * - 數值都放在 CSS 變數，換天氣時由 CSS transition 慢慢淡入淡出，不會閃一下。
 */
export default function WeatherBackdrop({ scene }) {
  const effects = useMemo(() => getEffects(scene), [scene])
  const reducedMotion = usePrefersReducedMotion()
  const canvasRef = useRef(null)
  const engineRef = useRef(null)
  const flashRef = useRef(null)

  // 引擎只在掛上時建立一次，卸載時停止動畫並移除事件
  useEffect(() => {
    const engine = createParticleEngine(canvasRef.current)
    engineRef.current = engine
    return () => {
      engine.destroy()
      engineRef.current = null
    }
  }, [])

  useEffect(() => {
    engineRef.current?.setReducedMotion(reducedMotion)
  }, [reducedMotion])

  const { precipitation, stars } = effects
  useEffect(() => {
    engineRef.current?.setConfig({ precipitation, stars })
  }, [precipitation, stars])

  // 閃電：隨機間隔觸發一次柔和的閃光；只改 class，不經過 React state，不會重新渲染
  const lightning = effects.lightning && !reducedMotion
  useEffect(() => {
    const flash = flashRef.current
    if (!lightning || !flash) return undefined
    let timer = 0
    const schedule = () => {
      const delay = LIGHTNING_MIN_MS + Math.random() * (LIGHTNING_MAX_MS - LIGHTNING_MIN_MS)
      timer = setTimeout(() => {
        flash.classList.remove('wx__flash--on')
        void flash.offsetWidth // 重新觸發 CSS 動畫
        flash.classList.add('wx__flash--on')
        schedule()
      }, delay)
    }
    schedule()
    return () => {
      clearTimeout(timer)
      flash.classList.remove('wx__flash--on')
    }
  }, [lightning])

  const style = {
    '--sun': effects.sun,
    '--moon': effects.moon,
    '--clouds': effects.clouds,
    '--fog': effects.fog,
  }
  if (effects.skyTop) {
    style['--sky-top'] = effects.skyTop
    style['--sky-bottom'] = effects.skyBottom
  }

  return (
    <div
      className="wx"
      aria-hidden="true"
      data-testid="weather-backdrop"
      data-kind={scene?.kind ?? 'idle'}
      data-night={scene?.night ? 'true' : 'false'}
      data-cloud-shade={effects.cloudShade}
      data-sky={effects.skyTop ? 'on' : 'off'}
      style={style}
    >
      <div className="wx__sky" />
      <div className="wx__sun">
        <div className="wx__sun-glow" />
        <div className="wx__sun-rays" />
        <div className="wx__flare" />
      </div>
      <div className="wx__moon" />
      <canvas ref={canvasRef} className="wx__canvas" />
      <div className="wx__clouds wx__clouds--far" />
      <div className="wx__clouds wx__clouds--near" />
      <div className="wx__fog wx__fog--a" />
      <div className="wx__fog wx__fog--b" />
      <div ref={flashRef} className="wx__flash" />
      <div className="wx__scrim" />
    </div>
  )
}
