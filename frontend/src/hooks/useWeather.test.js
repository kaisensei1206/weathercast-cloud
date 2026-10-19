import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useWeather } from './useWeather.js'
import { fetchWeather } from '../api/weatherApi.js'
import { TAINAN } from '../test/fixtures.js'

vi.mock('../api/weatherApi.js', () => ({ fetchWeather: vi.fn() }))

describe('useWeather', () => {
  it('keeps only the latest result when an older request finishes last', async () => {
    let resolveSlow
    const taipei = { ...TAINAN, city: { id: 'taipei', name: '臺北市', name_en: 'Taipei' } }
    fetchWeather
      .mockReturnValueOnce(new Promise((resolve) => (resolveSlow = resolve)))
      .mockResolvedValueOnce(taipei)
    const { result } = renderHook(() => useWeather())

    act(() => {
      result.current.search('Tainan')
    })
    await act(() => result.current.search('Taipei'))
    expect(result.current.data.city.id).toBe('taipei')

    await act(async () => resolveSlow(TAINAN))
    expect(result.current).toMatchObject({ status: 'success', city: 'Taipei' })
    expect(result.current.data.city.id).toBe('taipei')
  })

  it('does nothing on retry before the first search', () => {
    const { result } = renderHook(() => useWeather())

    act(() => result.current.retry())

    expect(fetchWeather).not.toHaveBeenCalled()
    expect(result.current.status).toBe('idle')
  })

  it('retries the last city', async () => {
    fetchWeather.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(TAINAN)
    const { result } = renderHook(() => useWeather())

    await act(() => result.current.search('Tainan'))
    expect(result.current.status).toBe('error')
    act(() => result.current.retry())

    await waitFor(() => expect(result.current.status).toBe('success'))
    expect(fetchWeather).toHaveBeenLastCalledWith('Tainan')
  })
})
