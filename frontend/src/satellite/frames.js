// 衛星雲圖的圖層與時間。
//
// 圖磚來自 NASA GIBS（Global Imagery Browse Services）：免費、不用金鑰，瀏覽器直接下載，
// 不經過我們的 Lambda，所以不增加 AWS 費用。

// 日本向日葵衛星（Himawari）AHI 第 13 波段「乾淨紅外線」：白天晚上都看得到雲，
// 越冷（越高）的雲越亮，颱風的螺旋雲帶和颱風眼很清楚
export const SATELLITE_LAYER = 'Himawari_AHI_Band13_Clean_Infrared'
export const TILE_MATRIX_SET = 'GoogleMapsCompatible_Level6'
export const MAX_NATIVE_ZOOM = 6

export const FRAME_INTERVAL_MINUTES = 10 // 向日葵每 10 分鐘拍一次全圓盤影像
export const FRAME_COUNT = 12 // 最近 2 小時
// 影像拍攝後要一段時間才會出現在 GIBS。2026-10-21 08:25Z 實測最新一張是 07:30Z（約晚 55 分鐘），
// 抓 70 分鐘的緩衝，太接近現在的時間會拿到空白圖磚
export const PUBLISH_DELAY_MINUTES = 70

const MINUTE = 60_000

/** 依現在時間算出要播放的影像時間（由舊到新），格式是 GIBS 要的 2026-10-21T07:20:00Z。 */
export function frameTimes(now = new Date()) {
  const step = FRAME_INTERVAL_MINUTES * MINUTE
  const latest = Math.floor((now.getTime() - PUBLISH_DELAY_MINUTES * MINUTE) / step) * step
  return Array.from({ length: FRAME_COUNT }, (_, i) =>
    new Date(latest - (FRAME_COUNT - 1 - i) * step).toISOString().replace('.000Z', 'Z'),
  )
}

/** Leaflet 用的圖磚網址樣板；{z}/{y}/{x} 由 Leaflet 代入。 */
export function tileUrl(time, layer = SATELLITE_LAYER) {
  return (
    `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layer}/default/${time}/` +
    `${TILE_MATRIX_SET}/{z}/{y}/{x}.png`
  )
}

const taipeiTime = new Intl.DateTimeFormat('zh-TW', {
  timeZone: 'Asia/Taipei',
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** 顯示用：轉成臺灣時間，例如「10/21 15:20」。 */
export function formatTaipeiTime(time) {
  const parts = Object.fromEntries(taipeiTime.formatToParts(new Date(time)).map((p) => [p.type, p.value]))
  return `${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`
}
