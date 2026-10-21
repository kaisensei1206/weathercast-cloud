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

// /api/typhoons 回傳的一個颱風（格式見 backend/src/typhoon_client.py 的 parse_typhoon）
export const TYPHOON = {
  name: '鳳凰',
  name_en: 'FUNG-WONG',
  number: '26',
  current: {
    time: '2026-10-20T14:00:00+08:00',
    lat: 19,
    lon: 127,
    max_wind_ms: 38,
    max_gust_ms: 48,
    pressure_hpa: 955,
    moving_speed_kmh: 20,
    moving_direction: 'WNW',
    radius_15ms_km: 250,
  },
  track: [
    { time: '2026-10-20T08:00:00+08:00', lat: 18.5, lon: 128 },
    { time: '2026-10-20T14:00:00+08:00', lat: 19, lon: 127 },
  ],
  forecast: [
    { time: '2026-10-21T14:00:00+08:00', lat: 20.5, lon: 124.5, tau_hours: 24, radius_70pct_km: 120 },
    { time: '2026-10-22T14:00:00+08:00', lat: 22.5, lon: 122, tau_hours: 48, radius_70pct_km: null },
  ],
}
