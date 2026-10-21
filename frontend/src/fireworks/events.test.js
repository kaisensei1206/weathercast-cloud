import { describe, expect, it } from 'vitest'
import { FIREWORKS } from '../test/fixtures.js'
import {
  countByKind,
  eventStatus,
  filterEvents,
  formatDateRange,
  formatPlace,
  safeUrl,
} from './events.js'

const [chenggong, sunMoonLake, yonghe] = FIREWORKS.events
const NOW = new Date('2026-10-21T17:00:00+08:00')

describe('eventStatus', () => {
  it('tells past, ongoing and upcoming events apart', () => {
    expect(eventStatus(chenggong, NOW)).toBe('past')
    expect(eventStatus(sunMoonLake, NOW)).toBe('ongoing')
    expect(eventStatus(yonghe, NOW)).toBe('upcoming')
  })

  it('counts the start and end moments as ongoing', () => {
    expect(eventStatus(chenggong, new Date(chenggong.start))).toBe('ongoing')
    expect(eventStatus(chenggong, new Date(chenggong.end))).toBe('ongoing')
  })

  it('uses the start time when there is no end time', () => {
    const { end: _end, ...single } = chenggong
    expect(eventStatus(single, new Date('2026-02-16T21:30:00+08:00'))).toBe('past')
  })
})

describe('filters', () => {
  it('counts each kind', () => {
    expect(countByKind(FIREWORKS.events)).toEqual({ all: 3, fireworks: 2, maybe: 1 })
    expect(countByKind([])).toEqual({ all: 0, fireworks: 0, maybe: 0 })
  })

  it('filters by kind', () => {
    expect(filterEvents(FIREWORKS.events, 'all')).toHaveLength(3)
    expect(filterEvents(FIREWORKS.events, 'maybe').map((e) => e.id)).toEqual(['yonghe'])
  })
})

describe('formatting', () => {
  it('shows one day or a range, in Taiwan time', () => {
    expect(formatDateRange(chenggong)).toBe('2/16')
    expect(formatDateRange(sunMoonLake)).toBe('9/12 – 11/14')
    // 16:00 UTC 前一天，臺灣已經是隔天
    expect(formatDateRange({ start: '2026-08-28T16:00:00Z' })).toBe('8/29')
  })

  it('joins city, town and address', () => {
    expect(formatPlace(chenggong)).toBe('臺東縣成功鎮 海濱公園')
    expect(formatPlace(sunMoonLake)).toBe('南投縣魚池鄉')
    expect(formatPlace({})).toBe('')
  })

  it('only allows http and https links', () => {
    expect(safeUrl(sunMoonLake.url)).toBe(sunMoonLake.url)
    expect(safeUrl('http://example.com')).toBe('http://example.com/')
    expect(safeUrl(yonghe.url)).toBeNull()
    expect(safeUrl(null)).toBeNull()
    expect(safeUrl('not a url')).toBeNull()
  })
})
