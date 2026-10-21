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

// /api/fireworks 回傳的活動（格式見 backend/src/fireworks_client.py 的 parse_event）
export const FIREWORKS = {
  year: 2026,
  events: [
    {
      id: 'chenggong',
      name: '2026成功鎮花火之夜',
      kind: 'fireworks',
      start: '2026-02-16T21:00:00+08:00',
      end: '2026-02-16T23:59:59+08:00',
      city: '臺東縣',
      town: '成功鎮',
      address: '海濱公園',
      lat: 23.10404,
      lon: 121.38497,
      url: null,
      image: null,
      organizer: null,
    },
    {
      id: 'sunmoonlake',
      name: '2026日月潭花火音樂嘉年華',
      kind: 'fireworks',
      start: '2026-09-12T00:00:00+08:00',
      end: '2026-11-14T00:00:00+08:00',
      city: '南投縣',
      town: '魚池鄉',
      address: '',
      lat: 23.8645,
      lon: 120.9119,
      url: 'https://www.sunmoonlake.gov.tw/Events/Activitys',
      image: null,
      organizer: '交通部觀光署',
    },
    {
      id: 'yonghe',
      name: '2026 樂動川端．點亮藝文廊道',
      kind: 'maybe',
      start: '2026-10-22T16:00:00+08:00',
      end: '2026-10-23T15:59:59+08:00',
      city: '新北市',
      town: '永和區',
      address: '',
      lat: 25.01949,
      lon: 121.51714,
      url: 'javascript:alert(1)',
      image: null,
      organizer: null,
    },
  ],
  meta: { source: 'upstream', stale: false, fetched_at: 1792148400, provider: 'taiwan-tourism' },
}
