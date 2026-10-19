import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiUrl, fetchCities, fetchWeather } from './weatherApi.js'
import { CITIES, TAINAN, jsonResponse } from '../test/fixtures.js'

let fetchMock

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.useRealTimers()
})

async function errorOf(promise) {
  try {
    await promise
  } catch (error) {
    return error
  }
  throw new Error('expected the call to fail')
}

describe('apiUrl', () => {
  it('uses a relative path when no base URL is set', () => {
    expect(apiUrl('/api/health', '')).toBe('/api/health')
  })

  it('joins the base URL without a double slash', () => {
    expect(apiUrl('/api/health', 'https://example.com/')).toBe('https://example.com/api/health')
  })
})

describe('fetchWeather', () => {
  it('returns the weather and encodes the city', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, TAINAN))

    await expect(fetchWeather(' 臺南 ')).resolves.toEqual(TAINAN)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`/api/weather?city=${encodeURIComponent('臺南')}`)
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it.each([
    ['', '請輸入城市名稱'],
    ['   ', '請輸入城市名稱'],
    ['x'.repeat(51), '最多 50 個字'],
  ])('rejects invalid input %j without calling the API', async (city, message) => {
    const error = await errorOf(fetchWeather(city))
    expect(error).toBeInstanceOf(ApiError)
    expect(error.kind).toBe('invalid_input')
    expect(error.message).toContain(message)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each([
    [404, { error: 'city_not_found', message: '找不到城市：Tokyo' }, 'not_found'],
    [400, { error: 'missing_city', message: '請提供 city 參數' }, 'invalid_input'],
    [502, { error: 'upstream_error', message: '氣象資料來源暫時無法使用' }, 'server'],
    [504, { error: 'upstream_timeout', message: '氣象資料來源回應逾時' }, 'server'],
    [500, { error: 'internal_error', message: '伺服器發生錯誤' }, 'server'],
    [404, { error: 'not_found', message: '找不到這個路徑' }, 'server'],
  ])('maps HTTP %i %j to kind %s', async (status, body, kind) => {
    fetchMock.mockResolvedValue(jsonResponse(status, body))

    const error = await errorOf(fetchWeather('Tokyo'))
    expect(error).toMatchObject({ kind, status, code: body.error, message: body.message })
  })

  it('treats a non-JSON error page as a server error', async () => {
    fetchMock.mockResolvedValue(jsonResponse(503, undefined))

    const error = await errorOf(fetchWeather('Tainan'))
    expect(error).toMatchObject({ kind: 'server', status: 503, message: '伺服器回應 503' })
  })

  it('treats a 200 response that is not JSON as a server error', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, undefined))

    const error = await errorOf(fetchWeather('Tainan'))
    expect(error.kind).toBe('server')
  })

  it('reports a network failure', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await errorOf(fetchWeather('Tainan'))
    expect(error.kind).toBe('network')
  })

  it('aborts and reports a timeout when the server does not answer', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(
      (url, { signal }) =>
        new Promise((resolve, reject) => {
          signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )

    const pending = errorOf(fetchWeather('Tainan', { timeoutMs: 5000 }))
    await vi.advanceTimersByTimeAsync(5000)
    expect((await pending).kind).toBe('timeout')
  })
})

describe('fetchCities', () => {
  it('returns the city list', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { cities: CITIES }))

    await expect(fetchCities()).resolves.toEqual(CITIES)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/cities')
  })

  it('returns an empty list when the body has no cities', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}))

    await expect(fetchCities()).resolves.toEqual([])
  })
})
