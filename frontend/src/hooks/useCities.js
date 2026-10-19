import { useEffect, useState } from 'react'
import { fetchCities } from '../api/weatherApi.js'

/** 預設城市清單。載入失敗只回傳空清單：使用者仍然可以自己輸入城市名稱。 */
export function useCities() {
  const [cities, setCities] = useState([])

  useEffect(() => {
    let cancelled = false
    fetchCities()
      .then((list) => {
        if (!cancelled) setCities(list)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  return cities
}
