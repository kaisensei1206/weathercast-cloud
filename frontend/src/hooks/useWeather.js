import { useCallback, useRef, useState } from 'react'
import { fetchWeather } from '../api/weatherApi.js'

const INITIAL = { status: 'idle', data: null, error: null, city: '' }

/**
 * 查詢天氣的狀態：idle → loading → success / error。
 * 連續查詢時只採用最後一次的結果，避免較慢的舊回應蓋掉新的結果。
 */
export function useWeather() {
  const [state, setState] = useState(INITIAL)
  const latestRequest = useRef(0)

  const search = useCallback(async (city) => {
    const requestId = ++latestRequest.current
    setState({ status: 'loading', data: null, error: null, city })
    try {
      const data = await fetchWeather(city)
      if (requestId === latestRequest.current) {
        setState({ status: 'success', data, error: null, city })
      }
    } catch (error) {
      if (requestId === latestRequest.current) {
        setState({ status: 'error', data: null, error, city })
      }
    }
  }, [])

  const retry = useCallback(() => {
    if (state.city) search(state.city)
  }, [search, state.city])

  return { ...state, search, retry }
}
