import { describe, expect, it } from 'vitest'
import {
  FRAME_COUNT,
  PUBLISH_DELAY_MINUTES,
  formatTaipeiTime,
  frameTimes,
  tileUrl,
} from './frames.js'

describe('frameTimes', () => {
  it('returns the last 2 hours in 10-minute steps, oldest first, ending before the publish delay', () => {
    const now = new Date('2026-10-21T08:25:30Z')
    const times = frameTimes(now)
    expect(times).toHaveLength(FRAME_COUNT)
    expect(PUBLISH_DELAY_MINUTES).toBe(70)
    expect(times.at(-1)).toBe('2026-10-21T07:10:00Z') // 08:25 - 70 分 = 07:15，往前取整到 07:10
    expect(times[0]).toBe('2026-10-21T05:20:00Z')
    for (let i = 1; i < times.length; i++) {
      expect(Date.parse(times[i]) - Date.parse(times[i - 1])).toBe(10 * 60_000)
    }
  })

  it('crosses midnight and month boundaries in UTC', () => {
    const times = frameTimes(new Date('2026-11-01T00:30:00Z'))
    expect(times.at(-1)).toBe('2026-10-31T23:20:00Z')
  })

  it('uses the GIBS time format without milliseconds', () => {
    for (const time of frameTimes(new Date('2026-10-21T08:25:00Z'))) {
      expect(time).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d0:00Z$/)
    }
  })
})

describe('tileUrl', () => {
  it('builds the GIBS WMTS template that Leaflet fills in', () => {
    expect(tileUrl('2026-10-21T07:30:00Z')).toBe(
      'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/Himawari_AHI_Band13_Clean_Infrared/default/' +
        '2026-10-21T07:30:00Z/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png',
    )
  })
})

describe('formatTaipeiTime', () => {
  it('shows Taiwan time (UTC+8)', () => {
    expect(formatTaipeiTime('2026-10-21T07:30:00Z')).toBe('10/21 15:30')
    expect(formatTaipeiTime('2026-10-31T20:00:00Z')).toBe('11/1 04:00')
  })
})
