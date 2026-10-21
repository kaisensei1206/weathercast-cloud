// 所有後端呼叫都在這個檔案：組網址、逾時、把各種失敗整理成 ApiError。
// 元件只看 ApiError.kind 決定顯示什麼，不需要知道 HTTP 細節。
import { API_BASE_URL, REQUEST_TIMEOUT_MS } from './config.js'

export const MAX_CITY_LENGTH = 50 // 和後端的 invalid_city 限制一致

/**
 * kind 的種類：
 *   invalid_input 輸入有誤（400）
 *   not_found     找不到城市（404 city_not_found）
 *   network       連不到伺服器（斷網、DNS、CORS 被擋）
 *   timeout       超過 REQUEST_TIMEOUT_MS 沒有回應
 *   server        伺服器錯誤（5xx、非預期的狀態碼或回應格式）
 */
export class ApiError extends Error {
  constructor(kind, message, { status = null, code = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
  }
}

export function apiUrl(path, baseUrl = API_BASE_URL) {
  return `${baseUrl.replace(/\/+$/, '')}${path}`
}

function kindFromStatus(status, body) {
  if (status === 400) return 'invalid_input'
  if (status === 404 && body?.error === 'city_not_found') return 'not_found'
  return 'server'
}

async function getJson(path, { baseUrl, timeoutMs = REQUEST_TIMEOUT_MS } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    let response
    try {
      response = await fetch(apiUrl(path, baseUrl), {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      })
    } catch {
      if (controller.signal.aborted) {
        throw new ApiError('timeout', '伺服器太久沒有回應，請稍後再試')
      }
      throw new ApiError('network', '無法連線到伺服器，請檢查網路後再試')
    }

    let body = null
    try {
      body = await response.json()
    } catch {
      // 回應不是 JSON，例如 API Gateway 或 CloudFront 的 HTML 錯誤頁
    }

    if (!response.ok) {
      throw new ApiError(
        kindFromStatus(response.status, body),
        body?.message ?? `伺服器回應 ${response.status}`,
        { status: response.status, code: body?.error ?? null },
      )
    }
    if (body === null) {
      throw new ApiError('server', '伺服器回應的格式不正確', { status: response.status })
    }
    return body
  } finally {
    clearTimeout(timer)
  }
}

/** GET /api/weather?city=...，回傳後端的 { city, current, meta } */
export async function fetchWeather(city, options) {
  const query = (city ?? '').trim()
  if (!query) throw new ApiError('invalid_input', '請輸入城市名稱')
  if (query.length > MAX_CITY_LENGTH) {
    throw new ApiError('invalid_input', `城市名稱最多 ${MAX_CITY_LENGTH} 個字`)
  }
  return getJson(`/api/weather?city=${encodeURIComponent(query)}`, options)
}

/** GET /api/cities，回傳 [{ id, name, name_en }] */
export async function fetchCities(options) {
  const body = await getJson('/api/cities', options)
  return Array.isArray(body.cities) ? body.cities : []
}

/** GET /api/fireworks，回傳 { year, events, meta }；events 是今年全臺的煙火相關活動 */
export async function fetchFireworks(options) {
  const body = await getJson('/api/fireworks', options)
  return {
    year: body.year,
    events: Array.isArray(body.events) ? body.events : [],
    meta: body.meta ?? {},
  }
}
