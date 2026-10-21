import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import L from 'leaflet'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchFireworks } from '../api/weatherApi.js'
import { FIREWORKS } from '../test/fixtures.js'
import FireworksMap from './FireworksMap.jsx'

// jsdom 沒有真的版面，換成假的 Leaflet，只檢查元件怎麼使用它。
// vitest 設定了 restoreMocks，vi.fn() 的實作每個測試都會被清掉，所以回傳值用一般函式。
vi.mock('leaflet', () => {
  const map = {
    fitBounds() {
      return this
    },
    flyTo: vi.fn(),
    remove: vi.fn(),
  }
  const group = {
    layers: [],
    addTo() {
      return this
    },
    clearLayers() {
      this.layers = []
    },
  }
  const marker = vi.fn((latLng, options) => {
    const m = {
      latLng,
      options,
      popup: null,
      openPopup: vi.fn(),
      bindPopup(content) {
        m.popup = content
        return m
      },
      addTo(target) {
        target.layers.push(m)
        return m
      },
    }
    return m
  })
  return {
    default: {
      map: vi.fn(() => map),
      tileLayer: vi.fn(() => ({ addTo() {} })),
      layerGroup: vi.fn(() => group),
      marker,
      divIcon: vi.fn((options) => options),
    },
  }
})

vi.mock('../api/weatherApi.js', () => ({ fetchFireworks: vi.fn() }))

const group = () => L.layerGroup.mock.results[0].value
const markerNames = () => group().layers.map((m) => m.options.title)

describe('FireworksMap', () => {
  beforeEach(() => {
    L.map.mockClear()
    L.layerGroup.mockClear()
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-21T17:00:00+08:00'))
    fetchFireworks.mockResolvedValue(FIREWORKS)
  })

  it('shows every event on the map and in the list', async () => {
    render(<FireworksMap />)

    expect(await screen.findByText('2026日月潭花火音樂嘉年華')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '煙火地圖' })).toBeInTheDocument()
    expect(screen.getByText(/2026 年全臺的煙火活動/)).toBeInTheDocument()
    expect(markerNames()).toEqual(FIREWORKS.events.map((e) => e.name))
    expect(L.map).toHaveBeenCalledTimes(1)
    expect(L.map.mock.calls[0][1]).toMatchObject({ scrollWheelZoom: false })
  })

  it('marks each event as past, ongoing or upcoming, and fireworks or maybe', async () => {
    render(<FireworksMap />)
    await screen.findByRole('list')

    const [chenggong, sunMoonLake, yonghe] = screen.getAllByRole('listitem')
    expect(chenggong).toHaveTextContent('已結束')
    expect(sunMoonLake).toHaveTextContent('進行中')
    expect(yonghe).toHaveTextContent('即將舉行')
    expect(yonghe).toHaveTextContent('可能有煙火')
    expect(chenggong).not.toHaveTextContent('可能有煙火')

    const icons = group().layers.map((m) => m.options.icon.className)
    expect(icons[0]).toContain('fw-marker--fireworks fw-marker--past')
    expect(icons[2]).toContain('fw-marker--maybe fw-marker--upcoming')
  })

  it('filters by kind and shows the counts', async () => {
    const user = userEvent.setup()
    render(<FireworksMap />)

    const filters = within(await screen.findByRole('group', { name: '活動類型' }))
    expect(filters.getByRole('button', { name: /全部\s*3/ })).toHaveAttribute('aria-pressed', 'true')
    await user.click(filters.getByRole('button', { name: /可能有煙火\s*1/ }))

    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(markerNames()).toEqual(['2026 樂動川端．點亮藝文廊道'])
  })

  it('flies to an event and opens its details from the list', async () => {
    const user = userEvent.setup()
    render(<FireworksMap />)

    await user.click(await screen.findByRole('button', { name: /日月潭/ }))

    const map = L.map.mock.results[0].value
    expect(map.flyTo).toHaveBeenCalledWith([23.8645, 120.9119], 11, expect.any(Object))
    expect(group().layers[1].openPopup).toHaveBeenCalled()
  })

  it('builds popups as text, never as HTML, and drops unsafe links', async () => {
    render(<FireworksMap />)
    await screen.findByRole('list')

    const sunMoonLake = group().layers[1].popup()
    expect(sunMoonLake.textContent).toContain('9/12 – 11/14・進行中・煙火大會')
    expect(sunMoonLake.querySelector('a').href).toBe('https://www.sunmoonlake.gov.tw/Events/Activitys')

    const yonghe = group().layers[2].popup()
    expect(yonghe.querySelector('a')).toBeNull() // javascript: 連結不會出現
  })

  it('shows HTML in event data as plain text', async () => {
    const name = '<img src=x onerror=alert(1)>'
    fetchFireworks.mockResolvedValue({ ...FIREWORKS, events: [{ ...FIREWORKS.events[0], name }] })
    render(<FireworksMap />)
    await screen.findByRole('list')

    const popup = group().layers[0].popup()
    expect(popup.querySelector('img')).toBeNull()
    expect(popup.textContent).toContain(name)
  })

  it('says so when a filter has no events', async () => {
    fetchFireworks.mockResolvedValue({ ...FIREWORKS, events: [] })
    render(<FireworksMap />)
    expect(await screen.findByText('今年目前沒有這類活動。')).toBeInTheDocument()
  })

  it('shows an error when the data cannot be loaded', async () => {
    fetchFireworks.mockRejectedValue(new Error('502'))
    render(<FireworksMap />)
    expect(await screen.findByRole('alert')).toHaveTextContent('活動資料暫時無法取得')
  })

  it('ignores an answer that arrives after unmount and removes the map', async () => {
    let resolve
    fetchFireworks.mockReturnValue(new Promise((r) => (resolve = r)))
    const { unmount } = render(<FireworksMap />)
    const map = L.map.mock.results[0].value
    unmount()
    await act(async () => resolve(FIREWORKS))
    expect(map.remove).toHaveBeenCalled()
    expect(group().layers).toEqual([])
  })
})
