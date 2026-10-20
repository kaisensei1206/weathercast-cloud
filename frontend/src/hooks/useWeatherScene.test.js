import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TAINAN } from '../test/fixtures.js'
import { IDLE_SCENE } from '../weather/scene.js'
import { useWeatherScene } from './useWeatherScene.js'

describe('useWeatherScene', () => {
  it('starts idle and follows successful results', () => {
    const { result, rerender } = renderHook(({ status, data }) => useWeatherScene(status, data), {
      initialProps: { status: 'idle', data: null },
    })
    expect(result.current).toBe(IDLE_SCENE)

    rerender({ status: 'success', data: TAINAN })
    expect(result.current.kind).toBe('rain')
  })

  it('returns the same object for the same data so effects are not reset', () => {
    const { result, rerender } = renderHook(({ status, data }) => useWeatherScene(status, data), {
      initialProps: { status: 'success', data: TAINAN },
    })
    const first = result.current
    rerender({ status: 'success', data: TAINAN })
    expect(result.current).toBe(first)
  })

  it('keeps the previous scene while the next city loads', () => {
    const { result, rerender } = renderHook(({ status, data }) => useWeatherScene(status, data), {
      initialProps: { status: 'success', data: TAINAN },
    })
    const tainan = result.current
    rerender({ status: 'loading', data: null })
    expect(result.current).toBe(tainan)
  })

  it('goes back to idle on errors, and stays idle while retrying', () => {
    const { result, rerender } = renderHook(({ status, data }) => useWeatherScene(status, data), {
      initialProps: { status: 'success', data: TAINAN },
    })
    rerender({ status: 'error', data: null })
    expect(result.current).toBe(IDLE_SCENE)
    rerender({ status: 'loading', data: null })
    expect(result.current).toBe(IDLE_SCENE)
  })
})
