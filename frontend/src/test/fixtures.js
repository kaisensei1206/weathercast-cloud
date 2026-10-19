// 測試共用的假資料，格式和後端 README 的範例相同
export const TAINAN = {
  city: { id: 'tainan', name: '臺南市', name_en: 'Tainan' },
  current: {
    time: '2026-10-16T19:00',
    temperature: 27.1,
    apparent_temperature: 29.9,
    humidity: 78,
    precipitation: 0.2,
    wind_speed: 9.4,
    weather_code: 61,
    description: '小雨',
  },
  meta: { source: 'upstream', stale: false, fetched_at: 1792148400, provider: 'open-meteo' },
}

export const CITIES = [
  { id: 'taipei', name: '臺北市', name_en: 'Taipei' },
  { id: 'tainan', name: '臺南市', name_en: 'Tainan' },
]

/** 模擬 fetch 回傳的 Response */
export function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new SyntaxError('Unexpected token <')
      return body
    },
  }
}
