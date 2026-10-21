import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import L from 'leaflet'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FRAME_COUNT } from '../satellite/frames.js'
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
  return { default: { map: vi.fn(() => map), tileLayer } }
})

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
})
