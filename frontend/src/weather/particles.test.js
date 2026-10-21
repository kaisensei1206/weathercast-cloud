import { afterEach, describe, expect, it, vi } from 'vitest'
import { createParticleEngine, particleBudget, targetCounts } from './particles.js'

describe('particleBudget', () => {
  it('is 1 on a large screen with plenty of cores', () => {
    expect(particleBudget({ width: 1920, height: 1080, cores: 8 })).toBe(1)
  })

  it('draws fewer particles on phones and slow CPUs', () => {
    const desktop = particleBudget({ width: 1280, height: 800, cores: 8 })
    const phone = particleBudget({ width: 390, height: 844, cores: 8 })
    const slowPhone = particleBudget({ width: 390, height: 844, cores: 2 })
    expect(phone).toBeLessThan(desktop)
    expect(slowPhone).toBeLessThan(phone)
    expect(slowPhone).toBeGreaterThanOrEqual(0.25)
  })
})

describe('targetCounts', () => {
  it('counts only the active precipitation type', () => {
    const rain = { type: 'rain', density: 1 }
    expect(targetCounts({ precipitation: rain }, 1)).toEqual({ rain: 260, snow: 0 })
    expect(targetCounts({ precipitation: { type: 'snow', density: 0.5 } }, 0.5)).toEqual({
      rain: 0,
      snow: 40,
    })
  })

  it('returns zero for no config', () => {
    expect(targetCounts(null, 1)).toEqual({ rain: 0, snow: 0 })
  })
})

function fakeCanvas() {
  const ctx = new Proxy(
    {},
    {
      get: (target, key) => (key in target ? target[key] : (target[key] = vi.fn())),
      set: (target, key, value) => {
        target[key] = value
        return true
      },
    },
  )
  return { ctx, canvas: { getContext: () => ctx, width: 0, height: 0 } }
}

describe('createParticleEngine', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('does nothing when canvas is not supported', () => {
    const engine = createParticleEngine({ getContext: () => null })
    expect(() => {
      engine.setConfig({ precipitation: { type: 'rain', density: 1 } })
      engine.setReducedMotion(true)
      engine.destroy()
    }).not.toThrow()
  })

  it('starts one animation loop and stops it on destroy', () => {
    const raf = vi.fn(() => 42)
    const caf = vi.fn()
    vi.stubGlobal('requestAnimationFrame', raf)
    vi.stubGlobal('cancelAnimationFrame', caf)
    const removeWindow = vi.spyOn(window, 'removeEventListener')
    const removeDocument = vi.spyOn(document, 'removeEventListener')
    const { ctx, canvas } = fakeCanvas()

    const engine = createParticleEngine(canvas)
    const rain = { type: 'rain', density: 1, speed: 1, length: 1, opacity: 0.5, wind: 0.1 }
    engine.setConfig({ precipitation: rain })
    engine.setConfig({ precipitation: { ...rain, density: 0.5 } })
    expect(raf).toHaveBeenCalledTimes(1) // 換設定不會多開一個迴圈

    engine.destroy()
    expect(caf).toHaveBeenCalledWith(42)
    expect(removeWindow).toHaveBeenCalledWith('resize', expect.any(Function))
    expect(removeDocument).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    expect(ctx.clearRect).toHaveBeenCalled()
  })

  it('draws a still frame without animating when motion is reduced', () => {
    const raf = vi.fn(() => 1)
    vi.stubGlobal('requestAnimationFrame', raf)
    const { ctx, canvas } = fakeCanvas()

    const engine = createParticleEngine(canvas, { reducedMotion: true })
    engine.setConfig({
      precipitation: { type: 'snow', density: 1, speed: 0.5, opacity: 0.8 },
    })
    expect(raf).not.toHaveBeenCalled()
    expect(ctx.arc).toHaveBeenCalled()
    engine.destroy()
  })

  it('stops the loop when the weather has nothing to draw', () => {
    const raf = vi.fn(() => 7)
    const caf = vi.fn()
    vi.stubGlobal('requestAnimationFrame', raf)
    vi.stubGlobal('cancelAnimationFrame', caf)
    const { canvas } = fakeCanvas()

    const engine = createParticleEngine(canvas)
    engine.setConfig({ precipitation: { type: 'rain', density: 1, speed: 1, length: 1, opacity: 0.5, wind: 0 } })
    expect(raf).toHaveBeenCalledTimes(1)
    engine.setConfig({ precipitation: null })
    expect(caf).toHaveBeenCalledWith(7)
    engine.destroy()
  })
})
