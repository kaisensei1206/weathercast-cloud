import { useRef } from 'react'
import { IDLE_SCENE, sceneFromWeather } from '../weather/scene.js'

/**
 * 依查詢狀態決定背景場景：
 * - 成功：用這次的天氣。
 * - 載入中：保留上一次的場景，換城市時背景不會先變空白再變回來。
 * - 尚未查詢或查詢失敗：回到預設背景。
 *
 * 同一份資料只計算一次，回傳同一個物件，背景元件就不會重新設定特效。
 */
export function useWeatherScene(status, data) {
  const cache = useRef({ data: undefined, scene: IDLE_SCENE })

  if (status === 'success') {
    if (cache.current.data !== data) {
      cache.current = { data, scene: sceneFromWeather(data) }
    }
    return cache.current.scene
  }
  if (status === 'loading') return cache.current.scene
  cache.current = { data: undefined, scene: IDLE_SCENE }
  return IDLE_SCENE
}
