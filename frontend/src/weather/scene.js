// 把後端的天氣資料轉成「場景」：天氣類別、強度、雲量、日夜。
// 特效只看場景，不看天氣描述文字，也不知道 API 的格式。

/**
 * 天氣類別：
 *   idle       還沒有天氣資料（剛打開網頁、查詢失敗）
 *   unknown    有資料，但天氣代碼無法辨識
 *   clear      晴
 *   cloudy     多雲
 *   overcast   陰
 *   drizzle    毛毛雨
 *   rain       雨、陣雨
 *   heavy-rain 大雨、強陣雨
 *   storm      雷雨
 *   snow       雪
 *   fog        霧
 */

// WMO 天氣代碼（Open-Meteo 的 weather_code）。intensity 是降水或霧的強度（0 到 1），cloudCover 是雲量。
const WMO_CODES = {
  0: { kind: 'clear', intensity: 0, cloudCover: 0 },
  1: { kind: 'clear', intensity: 0, cloudCover: 0.25 },
  2: { kind: 'cloudy', intensity: 0, cloudCover: 0.55 },
  3: { kind: 'overcast', intensity: 0, cloudCover: 0.95 },
  45: { kind: 'fog', intensity: 0.8, cloudCover: 0.3 },
  48: { kind: 'fog', intensity: 1, cloudCover: 0.3 },
  51: { kind: 'drizzle', intensity: 0.3, cloudCover: 0.7 },
  53: { kind: 'drizzle', intensity: 0.5, cloudCover: 0.75 },
  55: { kind: 'drizzle', intensity: 0.8, cloudCover: 0.8 },
  56: { kind: 'drizzle', intensity: 0.4, cloudCover: 0.75 },
  57: { kind: 'drizzle', intensity: 0.8, cloudCover: 0.8 },
  61: { kind: 'rain', intensity: 0.35, cloudCover: 0.85 },
  63: { kind: 'rain', intensity: 0.65, cloudCover: 0.9 },
  65: { kind: 'heavy-rain', intensity: 1, cloudCover: 1 },
  66: { kind: 'rain', intensity: 0.4, cloudCover: 0.85 },
  67: { kind: 'heavy-rain', intensity: 0.9, cloudCover: 1 },
  71: { kind: 'snow', intensity: 0.3, cloudCover: 0.8 },
  73: { kind: 'snow', intensity: 0.6, cloudCover: 0.85 },
  75: { kind: 'snow', intensity: 1, cloudCover: 0.95 },
  77: { kind: 'snow', intensity: 0.25, cloudCover: 0.8 },
  80: { kind: 'rain', intensity: 0.45, cloudCover: 0.75 },
  81: { kind: 'rain', intensity: 0.75, cloudCover: 0.85 },
  82: { kind: 'heavy-rain', intensity: 1, cloudCover: 1 },
  85: { kind: 'snow', intensity: 0.5, cloudCover: 0.85 },
  86: { kind: 'snow', intensity: 1, cloudCover: 0.95 },
  95: { kind: 'storm', intensity: 0.8, cloudCover: 1 },
  96: { kind: 'storm', intensity: 0.9, cloudCover: 1 },
  99: { kind: 'storm', intensity: 1, cloudCover: 1 },
}

const UNKNOWN = { kind: 'unknown', intensity: 0, cloudCover: 0.4 }

export const IDLE_SCENE = Object.freeze({
  kind: 'idle',
  intensity: 0,
  cloudCover: 0,
  night: false,
})

/** 只接受整數代碼；字串、null、或剛好是物件屬性名稱（例如 constructor）都算 unknown。 */
export function classifyCode(code) {
  return Number.isInteger(code) && Object.hasOwn(WMO_CODES, code) ? WMO_CODES[code] : UNKNOWN
}

// 臺灣的大約中心點。所有縣市的日出日落相差不到 15 分鐘，用一個點計算就夠了。
const TAIWAN_LAT = 23.7
const TAIWAN_LON = 120.96
const TAIWAN_UTC_OFFSET = 8
// 太陽上緣碰到地平線（含大氣折射）的高度角，日出日落的標準定義
const HORIZON_DEG = -0.833

const RAD = Math.PI / 180

/** 解析後端回傳的當地時間字串，例如 2026-10-16T19:00；格式不對回傳 null。 */
export function parseLocalTime(time) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(time ?? '')
  if (!match) return null
  const [year, month, day, hour, minute] = match.slice(1).map(Number)
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) return null
  return { year, month, day, hour, minute }
}

/**
 * 臺灣當地時間的太陽高度角（度），用 NOAA 的簡化公式，誤差約幾分鐘。
 * 後端沒有日夜欄位，所以由 current.time 計算，不需要改 API。
 */
export function solarElevation({ year, month, day, hour, minute }) {
  const dayOfYear = (Date.UTC(year, month - 1, day) - Date.UTC(year, 0, 0)) / 86_400_000
  const g = ((2 * Math.PI) / 365) * (dayOfYear - 1 + (hour - 12) / 24)
  const equationOfTime =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(g) -
      0.032077 * Math.sin(g) -
      0.014615 * Math.cos(2 * g) -
      0.040849 * Math.sin(2 * g))
  const declination =
    0.006918 -
    0.399912 * Math.cos(g) +
    0.070257 * Math.sin(g) -
    0.006758 * Math.cos(2 * g) +
    0.000907 * Math.sin(2 * g) -
    0.002697 * Math.cos(3 * g) +
    0.00148 * Math.sin(3 * g)
  const solarMinutes =
    hour * 60 + minute + equationOfTime + 4 * TAIWAN_LON - 60 * TAIWAN_UTC_OFFSET
  const hourAngle = (solarMinutes / 4 - 180) * RAD
  const lat = TAIWAN_LAT * RAD
  const cosZenith =
    Math.sin(lat) * Math.sin(declination) +
    Math.cos(lat) * Math.cos(declination) * Math.cos(hourAngle)
  return 90 - Math.acos(Math.min(1, Math.max(-1, cosZenith))) / RAD
}

/** 時間格式不對時當作白天，讓畫面維持明亮、文字容易閱讀。 */
export function isNight(time) {
  const local = parseLocalTime(time)
  return local ? solarElevation(local) < HORIZON_DEG : false
}

/** 由 GET /api/weather 的回應建立場景；資料缺失時回傳 unknown，不會丟出錯誤。 */
export function sceneFromWeather(data) {
  const current = data?.current
  if (!current) return IDLE_SCENE
  const { kind, intensity, cloudCover } = classifyCode(current.weather_code)
  return { kind, intensity, cloudCover, night: isNight(current.time) }
}
