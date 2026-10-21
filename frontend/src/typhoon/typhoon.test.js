import { describe, expect, it, vi } from 'vitest'
import { TYPHOON } from '../test/fixtures.js'
import { STYLE, describeTyphoon, directionName, drawTyphoons } from './typhoon.js'

// 假的 Leaflet：只記錄畫了什麼
function fakeLeaflet() {
  const drawn = []
  const layer = (kind) =>
    vi.fn((points, options) => {
      const item = { kind, points, options, tooltip: null }
      return {
        bindTooltip(text) {
          item.tooltip = text
          return this
        },
        addTo(group) {
          group.added.push(item)
          drawn.push(item)
          return this
        },
      }
    })
  const L = { polyline: layer('polyline'), circle: layer('circle'), circleMarker: layer('marker') }
  const group = { added: [], clearLayers: vi.fn(function () { this.added = [] }) }
  return { L, group, drawn }
}

describe('directionName', () => {
  it('translates compass codes and keeps unknown ones', () => {
    expect(directionName('WNW')).toBe('西北西')
    expect(directionName('N')).toBe('北')
    expect(directionName('???')).toBe('???')
    expect(directionName(undefined)).toBe('')
  })
})

describe('describeTyphoon', () => {
  it('summarises name, wind, pressure and movement', () => {
    expect(describeTyphoon(TYPHOON)).toBe(
      '鳳凰（FUNG-WONG），近中心最大風速 38 m/s，中心氣壓 955 hPa，向西北西 20 km/h',
    )
  })

  it('skips missing values', () => {
    const depression = {
      name: '熱帶性低氣壓',
      name_en: null,
      current: { max_wind_ms: null, pressure_hpa: 1000, moving_speed_kmh: null },
    }
    expect(describeTyphoon(depression)).toBe('熱帶性低氣壓，中心氣壓 1000 hPa')
  })
})

describe('drawTyphoons', () => {
  it('draws track, forecast, probability circles, gale circle and centre', () => {
    const { L, group, drawn } = fakeLeaflet()
    drawTyphoons(L, group, [TYPHOON])

    const [track, forecast, probability, gale, centre] = drawn
    expect(track).toMatchObject({ kind: 'polyline', points: [[18.5, 128], [19, 127]], options: STYLE.track })
    // 預測路徑從現在位置開始
    expect(forecast.points).toEqual([[19, 127], [20.5, 124.5], [22.5, 122]])
    expect(forecast.options.dashArray).toBeTruthy()
    // 只有一個預測點有 70% 機率半徑；單位換成公尺
    expect(probability).toMatchObject({ kind: 'circle', points: [20.5, 124.5] })
    expect(probability.options.radius).toBe(120_000)
    expect(gale.options.radius).toBe(250_000)
    expect(centre).toMatchObject({ kind: 'marker', points: [19, 127] })
    expect(centre.tooltip).toContain('鳳凰')
    expect(drawn).toHaveLength(5)
  })

  it('draws only the centre when there is no history or forecast', () => {
    const { L, group, drawn } = fakeLeaflet()
    const lone = {
      ...TYPHOON,
      track: TYPHOON.track.slice(-1),
      forecast: [{ lat: null, lon: 120 }],
      current: { ...TYPHOON.current, radius_15ms_km: null },
    }
    drawTyphoons(L, group, [lone])
    expect(drawn.map((d) => d.kind)).toEqual(['marker'])
  })

  it('clears the previous drawing first', () => {
    const { L, group } = fakeLeaflet()
    drawTyphoons(L, group, [TYPHOON])
    drawTyphoons(L, group, [])
    expect(group.clearLayers).toHaveBeenCalledTimes(2)
    expect(group.added).toEqual([])
  })
})
