import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { IDLE_SCENE } from '../weather/scene.js'
import WeatherBackdrop from './WeatherBackdrop.jsx'

const STORM = { kind: 'storm', intensity: 1, cloudCover: 1, night: false }
const CLEAR_NIGHT = { kind: 'clear', intensity: 0, cloudCover: 0, night: true }

function stubMatchMedia(matches) {
  const listeners = new Set()
  const query = {
    get matches() {
      return matches
    },
    addEventListener: (_, fn) => listeners.add(fn),
    removeEventListener: (_, fn) => listeners.delete(fn),
  }
  vi.stubGlobal('matchMedia', () => query)
  return {
    listeners,
    change(value) {
      matches = value
      for (const fn of listeners) fn()
    },
  }
}

describe('WeatherBackdrop', () => {
  afterEach(() => vi.useRealTimers())

  it('is decorative and never blocks clicks or screen readers', () => {
    render(<WeatherBackdrop scene={IDLE_SCENE} />)
    const backdrop = screen.getByTestId('weather-backdrop')
    expect(backdrop).toHaveAttribute('aria-hidden', 'true')
    expect(backdrop).toHaveClass('wx')
    expect(backdrop).toHaveAttribute('data-kind', 'idle')
    expect(backdrop).toHaveAttribute('data-sky', 'off')
  })

  it('exposes the scene and its strengths as attributes and CSS variables', () => {
    const { rerender } = render(<WeatherBackdrop scene={CLEAR_NIGHT} />)
    const backdrop = screen.getByTestId('weather-backdrop')
    expect(backdrop).toHaveAttribute('data-kind', 'clear')
    expect(backdrop).toHaveAttribute('data-night', 'true')
    expect(backdrop).toHaveAttribute('data-sky', 'on')
    expect(backdrop.style.getPropertyValue('--moon')).toBe('1')
    expect(backdrop.style.getPropertyValue('--sun')).toBe('0')
    expect(backdrop.style.getPropertyValue('--sky-top')).toBe('#0b1531')

    rerender(<WeatherBackdrop scene={STORM} />)
    expect(backdrop).toHaveAttribute('data-kind', 'storm')
    expect(backdrop).toHaveAttribute('data-cloud-shade', 'dark')
    expect(backdrop.style.getPropertyValue('--moon')).toBe('0')
  })

  it('renders without crashing when canvas and matchMedia are missing', () => {
    vi.stubGlobal('matchMedia', undefined)
    const { unmount } = render(<WeatherBackdrop scene={STORM} />)
    expect(screen.getByTestId('weather-backdrop')).toBeInTheDocument()
    unmount()
  })

  it('flashes lightning occasionally during storms and stops after unmount', () => {
    vi.useFakeTimers()
    stubMatchMedia(false)
    const { container, unmount } = render(<WeatherBackdrop scene={STORM} />)
    const flash = container.querySelector('.wx__flash')
    expect(flash).not.toHaveClass('wx__flash--on')

    act(() => vi.advanceTimersByTime(15_000))
    expect(flash).toHaveClass('wx__flash--on')

    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('removes the lightning timer when the weather changes', () => {
    vi.useFakeTimers()
    stubMatchMedia(false)
    const { rerender } = render(<WeatherBackdrop scene={STORM} />)
    expect(vi.getTimerCount()).toBe(1)
    rerender(<WeatherBackdrop scene={CLEAR_NIGHT} />)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('turns lightning off when the user prefers reduced motion', () => {
    vi.useFakeTimers()
    const media = stubMatchMedia(false)
    const { unmount } = render(<WeatherBackdrop scene={STORM} />)
    expect(vi.getTimerCount()).toBe(1)

    act(() => media.change(true))
    expect(vi.getTimerCount()).toBe(0)

    unmount()
    expect(media.listeners.size).toBe(0)
  })
})
