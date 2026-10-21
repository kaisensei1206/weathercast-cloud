// 煙火活動的顯示邏輯：狀態（即將舉行、進行中、已結束）、篩選、日期文字。
// 純函式，不碰 React 和 Leaflet，方便測試。

export const KIND_LABELS = {
  fireworks: '煙火大會',
  maybe: '可能有煙火',
}

export const STATUS_LABELS = {
  upcoming: '即將舉行',
  ongoing: '進行中',
  past: '已結束',
}

/** 依現在時間判斷活動狀態；時間字串含 +08:00，所以和使用者電腦的時區無關。 */
export function eventStatus(event, now = new Date()) {
  const start = new Date(event.start).getTime()
  const end = new Date(event.end ?? event.start).getTime()
  const t = now.getTime()
  if (t < start) return 'upcoming'
  if (t <= end) return 'ongoing'
  return 'past'
}

/** 每個種類有幾筆，給篩選按鈕顯示數字。 */
export function countByKind(events) {
  const counts = { all: events.length, fireworks: 0, maybe: 0 }
  for (const event of events) {
    if (event.kind in counts) counts[event.kind] += 1
  }
  return counts
}

export function filterEvents(events, kind) {
  return kind === 'all' ? events : events.filter((e) => e.kind === kind)
}

// 活動時間一律用臺灣時間顯示
const dateFormat = new Intl.DateTimeFormat('zh-TW', {
  timeZone: 'Asia/Taipei',
  month: 'numeric',
  day: 'numeric',
})

function dateParts(time) {
  return Object.fromEntries(dateFormat.formatToParts(new Date(time)).map((p) => [p.type, p.value]))
}

/** 「2/16」或「9/12 – 11/14」 */
export function formatDateRange(event) {
  const start = dateParts(event.start)
  const end = dateParts(event.end ?? event.start)
  const from = `${start.month}/${start.day}`
  const to = `${end.month}/${end.day}`
  return from === to ? from : `${from} – ${to}`
}

/** 「臺東縣成功鎮 海濱公園」 */
export function formatPlace(event) {
  return [`${event.city ?? ''}${event.town ?? ''}`, event.address].filter(Boolean).join(' ')
}

/** 只接受 http(s) 網址，避免資料裡的 javascript: 之類的連結被放進 href。 */
export function safeUrl(url) {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null
  } catch {
    return null
  }
}
