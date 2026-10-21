import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import L from 'leaflet'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchFireworks } from '../api/weatherApi.js'
import { FIREWORKS } from '../test/fixtures.js'
import FireworksMap from './FireworksMap.jsx'

// jsdom 沒有真的版面，換成假的 Leaflet，只檢查元件怎麼使用它。
// vitest 設定了 restoreMocks，vi.fn() 的實作每個測試都會被清掉，所以回傳值用一般函式。
// 假的投影：1 度 = 1 px，x 是經度、y 是緯度，方便算出地圖中心被移了多少。
vi.mock('leaflet', () => {
  const point = (x, y) => ({ x, y, subtract: ([dx, dy]) => point(x - dx, y - dy) })
  const map = {
    fitOptions: null,
    fitBounds(bounds, options) {
      this.fitOptions = options
      return this
    },
    project: ([lat, lon]) => point(lon, lat),
    unproject: (p) => [p.y, p.x],
    flyTo: vi.fn(),
    remove: vi.fn(),
  }
  const control = () => ({ addTo() {} })
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
      control: { attribution: control, zoom: control },
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

function setViewport(width, height) {
  window.innerWidth = width
  window.innerHeight = height
}

describe('FireworksMap', () => {
  beforeEach(() => {
    setViewport(1280, 800)
    window.scrollTo = vi.fn()
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
  })

  it('puts the map behind the whole page, outside the panel', async () => {
    const { container } = render(<FireworksMap />)
    await screen.findByRole('list')

    const map = screen.getByRole('region', { name: /煙火活動地圖/ })
    expect(map).toHaveClass('map-bg')
    expect(map.parentElement).toBe(document.body)
    expect(container).not.toContainElement(map)
    expect(L.map.mock.calls[0][0]).toBe(map)
  })

  it('fits Taiwan into the part of the screen the panel does not cover', async () => {
    render(<FireworksMap />)
    await screen.findByRole('list')
    expect(L.map.mock.results[0].value.fitOptions).toEqual({
      paddingTopLeft: [456, 24], // 桌面：左邊 432px 是面板
      paddingBottomRight: [24, 24],
    })
  })

  it('fits Taiwan above the bottom sheet on phones', async () => {
    setViewport(375, 800)
    render(<FireworksMap />)
    await screen.findByRole('list')
    expect(L.map.mock.results[0].value.fitOptions).toEqual({
      paddingTopLeft: [24, 24],
      paddingBottomRight: [24, 464], // 手機：下方 55%（440px）是面板
    })
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

    // 地圖中心往左移半個面板（216px），標記就落在右邊看得到的那一塊中間
    const map = L.map.mock.results[0].value
    expect(map.flyTo).toHaveBeenCalledWith([23.8645, 120.9119 - 216], 11, expect.any(Object))
    expect(group().layers[1].openPopup).toHaveBeenCalled()
    expect(window.scrollTo).not.toHaveBeenCalled()
  })

  it('on phones, keeps the event above the bottom sheet and scrolls back to the map', async () => {
    setViewport(375, 800)
    const user = userEvent.setup()
    render(<FireworksMap />)

    await user.click(await screen.findByRole('button', { name: /日月潭/ }))

    // 地圖中心往下移半個面板（220px），標記落在上方看得到的那一塊中間
    const map = L.map.mock.results[0].value
    expect(map.flyTo).toHaveBeenCalledWith([23.8645 + 220, 120.9119], 11, expect.any(Object))
    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
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
