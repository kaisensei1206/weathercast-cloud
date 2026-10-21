import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import L from 'leaflet'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchTyphoons } from '../api/weatherApi.js'
import { FRAME_COUNT } from '../satellite/frames.js'
import { TYPHOON } from '../test/fixtures.js'
import SatelliteMap from './SatelliteMap.jsx'

// jsdom 沒有真的版面和網路，換成假的 Leaflet，只檢查元件怎麼使用它
vi.mock('leaflet', () => {
  const map = { remove: vi.fn() }
  const tileLayer = vi.fn((url, options) => ({
    url,
    options,
    opacity: options.opacity,
    addTo() {
      return this
    },
    setOpacity: vi.fn(function (value) {
      this.opacity = value
    }),
  }))
  const group = {
    addTo() {
      return this
    },
    clearLayers() {},
  }
  const shape = () => ({
    bindTooltip() {
      return this
    },
    addTo() {
      return this
    },
  })
  return {
    default: {
      map: vi.fn(() => map),
      tileLayer,
      layerGroup: vi.fn(() => group),
      polyline: vi.fn(shape),
      circle: vi.fn(shape),
      circleMarker: vi.fn(shape),
    },
  }
})

vi.mock('../api/weatherApi.js', () => ({ fetchTyphoons: vi.fn() }))

const satelliteLayers = () => L.tileLayer.mock.results.map((r) => r.value).filter((l) => l.url.includes('gibs'))
const visibleIndex = () => satelliteLayers().findIndex((l) => l.opacity === 1)

function stubReducedMotion(matches) {
  vi.stubGlobal('matchMedia', () => ({ matches, addEventListener() {}, removeEventListener() {} }))
}

describe('SatelliteMap', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    L.map.mockClear()
    L.tileLayer.mockClear()
    L.circleMarker.mockClear()
    fetchTyphoons.mockReset()
    fetchTyphoons.mockResolvedValue([])
  })
  afterEach(() => vi.useRealTimers())

  it('creates the map once with one layer per frame, showing only the latest', () => {
    stubReducedMotion(false)
    const { rerender } = render(<SatelliteMap />)
    rerender(<SatelliteMap />)
    expect(L.map).toHaveBeenCalledTimes(1)
    expect(satelliteLayers()).toHaveLength(FRAME_COUNT)
    expect(visibleIndex()).toBe(FRAME_COUNT - 1)
    expect(L.map.mock.calls[0][1]).toMatchObject({ scrollWheelZoom: false })
  })

  it('plays the frames in a loop and can be paused', async () => {
    stubReducedMotion(false)
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SatelliteMap />)

    act(() => vi.advanceTimersByTime(1800)) // 最新一張停留後回到第一張
    expect(visibleIndex()).toBe(0)
    act(() => vi.advanceTimersByTime(600))
    expect(visibleIndex()).toBe(1)

    await user.click(screen.getByRole('button', { name: '暫停' }))
    act(() => vi.advanceTimersByTime(5000))
    expect(visibleIndex()).toBe(1)
    expect(screen.getByRole('button', { name: '播放' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('jumps to a frame from the timeline and stops playing', () => {
    stubReducedMotion(false)
    render(<SatelliteMap />)
    const slider = screen.getByRole('slider', { name: '影像時間' })
    fireEvent.change(slider, { target: { value: '3' } })
    expect(visibleIndex()).toBe(3)
    expect(screen.getByRole('button', { name: '播放' })).toBeInTheDocument()
    expect(screen.getByText(/（臺灣時間）/)).toHaveTextContent(/^\d{1,2}\/\d{1,2} \d{2}:\d{2}/)
    expect(screen.queryByRole('status')).not.toBeInTheDocument() // 時間不是 live region，播放時不會一直被念出來
  })

  it('does not autoplay when the user prefers reduced motion', () => {
    stubReducedMotion(true)
    render(<SatelliteMap />)
    act(() => vi.advanceTimersByTime(10_000))
    expect(visibleIndex()).toBe(FRAME_COUNT - 1)
    expect(screen.getByRole('button', { name: '播放' })).toBeInTheDocument()
  })

  it('removes the map and stops the timer on unmount', () => {
    stubReducedMotion(false)
    const { unmount } = render(<SatelliteMap />)
    const map = L.map.mock.results[0].value
    unmount()
    expect(map.remove).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('draws typhoons from the API on top of the clouds and lists them', async () => {
    stubReducedMotion(true)
    fetchTyphoons.mockResolvedValue([TYPHOON])
    render(<SatelliteMap />)

    expect(await screen.findByText(/鳳凰（FUNG-WONG）/)).toBeInTheDocument()
    await waitFor(() => expect(L.circleMarker).toHaveBeenCalledWith([19, 127], expect.any(Object)))
    expect(screen.getByText('預測路徑')).toBeInTheDocument()
  })

  it('says so when there is no typhoon', async () => {
    stubReducedMotion(true)
    render(<SatelliteMap />)
    expect(await screen.findByText('目前沒有颱風或熱帶性低氣壓。')).toBeInTheDocument()
  })

  it('shows only the clouds when typhoon data is unavailable', async () => {
    stubReducedMotion(true)
    fetchTyphoons.mockRejectedValue(new Error('503'))
    render(<SatelliteMap />)
    await waitFor(() => expect(fetchTyphoons).toHaveBeenCalled())
    await act(async () => {})
    expect(screen.queryByText(/颱風動態/)).not.toBeInTheDocument()
    expect(L.circleMarker).not.toHaveBeenCalled()
  })

  it('ignores a typhoon answer that arrives after unmount', async () => {
    stubReducedMotion(true)
    let resolve
    fetchTyphoons.mockReturnValue(new Promise((r) => (resolve = r)))
    const { unmount } = render(<SatelliteMap />)
    unmount()
    await act(async () => resolve([TYPHOON]))
    expect(L.circleMarker).not.toHaveBeenCalled()
  })
})
