import { describe, expect, it } from 'vitest'
import { TAINAN } from '../test/fixtures.js'
import {
  IDLE_SCENE,
  classifyCode,
  isNight,
  parseLocalTime,
  sceneFromWeather,
  solarElevation,
} from './scene.js'

describe('classifyCode', () => {
  it.each([
    [[0, 1], 'clear'],
    [[2], 'cloudy'],
    [[3], 'overcast'],
    [[45, 48], 'fog'],
    [[51, 53, 55, 56, 57], 'drizzle'],
    [[61, 63, 66, 80, 81], 'rain'],
    [[65, 67, 82], 'heavy-rain'],
    [[71, 73, 75, 77, 85, 86], 'snow'],
    [[95, 96, 99], 'storm'],
  ])('maps WMO codes %j to %s', (codes, kind) => {
    for (const code of codes) expect(classifyCode(code).kind).toBe(kind)
  })

  it.each([4, 100, -1, null, undefined, '61', 'rain', NaN, 61.5, 'constructor', 'toString'])('treats %j as unknown', (code) => {
    expect(classifyCode(code).kind).toBe('unknown')
  })

  it('gives heavier codes a higher intensity', () => {
    expect(classifyCode(51).intensity).toBeLessThan(classifyCode(55).intensity)
    expect(classifyCode(71).intensity).toBeLessThan(classifyCode(75).intensity)
    expect(classifyCode(2).cloudCover).toBeLessThan(classifyCode(3).cloudCover)
  })
})

describe('parseLocalTime', () => {
  it('reads the backend time format', () => {
    expect(parseLocalTime('2026-10-16T19:05')).toEqual({
      year: 2026,
      month: 10,
      day: 16,
      hour: 19,
      minute: 5,
    })
  })

  it.each([undefined, null, '', 'yesterday', '2026-13-01T10:00', '2026-10-16T25:00', 1792148400])(
    'returns null for %j',
    (value) => {
      expect(parseLocalTime(value)).toBeNull()
    },
  )
})

describe('isNight', () => {
  it.each([
    ['2026-10-16T12:00', false],
    ['2026-10-16T22:30', true],
    ['2026-10-16T03:00', true],
    ['2026-06-21T05:30', false], // 夏至日出約 05:05
    ['2026-06-21T04:40', true],
    ['2026-12-21T17:30', true], // 冬至日落約 17:10
    ['2026-12-21T16:45', false],
  ])('%s is night: %s', (time, expected) => {
    expect(isNight(time)).toBe(expected)
  })

  it('treats a missing or broken time as day', () => {
    expect(isNight(undefined)).toBe(false)
    expect(isNight('not a time')).toBe(false)
  })

  it('puts the sun high at noon and below the horizon at midnight', () => {
    expect(solarElevation({ year: 2026, month: 6, day: 21, hour: 12, minute: 0 })).toBeGreaterThan(80)
    expect(solarElevation({ year: 2026, month: 6, day: 21, hour: 0, minute: 0 })).toBeLessThan(-30)
  })
})

describe('sceneFromWeather', () => {
  it('builds a scene from an API response', () => {
    expect(sceneFromWeather(TAINAN)).toEqual({
      kind: 'rain',
      intensity: 0.35,
      cloudCover: 0.85,
      night: true, // 19:00 已經日落
    })
  })

  it.each([undefined, null, {}, { current: null }])('returns the idle scene for %j', (data) => {
    expect(sceneFromWeather(data)).toBe(IDLE_SCENE)
  })

  it('handles a missing code and time without throwing', () => {
    expect(sceneFromWeather({ current: {} })).toEqual({
      kind: 'unknown',
      intensity: 0,
      cloudCover: 0.4,
      night: false,
    })
  })
})
