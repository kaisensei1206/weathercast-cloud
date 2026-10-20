import { describe, expect, it } from 'vitest'
import { getEffects, skyTone } from './effects.js'
import { IDLE_SCENE, classifyCode } from './scene.js'

const scene = (code, night = false) => ({ ...classifyCode(code), night })

const KINDS = {
  clear: 0,
  cloudy: 2,
  overcast: 3,
  fog: 45,
  drizzle: 51,
  rain: 63,
  'heavy-rain': 65,
  snow: 73,
  storm: 95,
  unknown: 4,
}

describe('getEffects', () => {
  it.each(Object.entries(KINDS))('gives %s its own sky by day and by night', (_, code) => {
    const day = getEffects(scene(code))
    const night = getEffects(scene(code, true))
    expect(day.skyTop).toMatch(/^#[0-9a-f]{6}$/)
    expect(night.skyTop).not.toBe(day.skyTop)
    expect(day.tone).toBe('dark')
  })

  it('uses a different sky for every kind', () => {
    const skies = Object.values(KINDS).map((code) => getEffects(scene(code)).skyTop)
    expect(new Set(skies).size).toBe(skies.length)
  })

  it('shows the sun on clear days and the moon and stars on clear nights', () => {
    expect(getEffects(scene(0))).toMatchObject({ sun: 1, moon: 0, stars: 0 })
    expect(getEffects(scene(0, true))).toMatchObject({ sun: 0, moon: 1, stars: 1 })
  })

  it('makes overcast visibly heavier than cloudy', () => {
    const cloudy = getEffects(scene(2))
    const overcast = getEffects(scene(3))
    expect(overcast.clouds).toBeGreaterThan(cloudy.clouds + 0.3)
    expect(overcast.sun).toBe(0)
    expect(cloudy.sun).toBeGreaterThan(0)
    expect(overcast.fog).toBeGreaterThan(0)
  })

  it('scales rain from drizzle to heavy rain', () => {
    const [drizzle, rain, heavy] = [51, 63, 65].map((code) => getEffects(scene(code)).precipitation)
    expect(drizzle.type).toBe('rain')
    expect(drizzle.density).toBeLessThan(rain.density)
    expect(rain.density).toBeLessThan(heavy.density)
    expect(drizzle.speed).toBeLessThan(heavy.speed)
    expect(drizzle.length).toBeLessThan(heavy.length)
  })

  it('adds lightning and dark clouds only to thunderstorms', () => {
    const storm = getEffects(scene(95))
    expect(storm).toMatchObject({ lightning: true, cloudShade: 'dark' })
    expect(storm.precipitation.type).toBe('rain')
    for (const code of [0, 2, 3, 45, 51, 63, 65, 73]) {
      expect(getEffects(scene(code)).lightning).toBe(false)
    }
  })

  it('scales snowfall with intensity', () => {
    const light = getEffects(scene(71)).precipitation
    const heavy = getEffects(scene(75)).precipitation
    expect(light.type).toBe('snow')
    expect(light.density).toBeLessThan(heavy.density)
  })

  it('makes dense fog thicker than light fog', () => {
    expect(getEffects(scene(45)).fog).toBeLessThan(getEffects(scene(48)).fog)
  })

  it.each([IDLE_SCENE, undefined, null, { kind: 'nonsense' }])(
    'falls back to the plain page for %j',
    (value) => {
      expect(getEffects(value)).toMatchObject({
        skyTop: null,
        tone: null,
        precipitation: null,
        lightning: false,
      })
      expect(skyTone(value)).toBeNull()
    },
  )

  it('keeps every strength between 0 and 1', () => {
    for (const code of Object.values(KINDS)) {
      for (const night of [false, true]) {
        const effects = getEffects(scene(code, night))
        for (const key of ['sun', 'moon', 'stars', 'clouds', 'fog']) {
          expect(effects[key]).toBeGreaterThanOrEqual(0)
          expect(effects[key]).toBeLessThanOrEqual(1)
        }
        if (effects.precipitation) {
          expect(effects.precipitation.density).toBeLessThanOrEqual(1)
        }
      }
    }
  })
})
