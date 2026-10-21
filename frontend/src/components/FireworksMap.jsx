import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchFireworks } from '../api/weatherApi.js'
import {
  KIND_LABELS,
  STATUS_LABELS,
  countByKind,
  eventStatus,
  filterEvents,
  formatDateRange,
  formatPlace,
  safeUrl,
} from '../fireworks/events.js'

// 臺灣本島加上澎湖、金門的範圍；用 fitBounds，手機和桌面都剛好看到全臺
const TAIWAN_BOUNDS = [
  [21.8, 118.2],
  [25.4, 122.1],
]
// OpenStreetMap 官方圖磚：不需要金鑰（CARTO 的底圖在 localhost 以外的網域要 API 金鑰）。
// 用 CSS 把底圖轉成灰色（見 index.css 的 .map-bg），橘色的煙火標記比較顯眼
const BASE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

// 地圖是整個畫面的背景，有一部分被查詢面板蓋住，數字要和 index.css 的 .app 一致：
// 桌面的面板在左邊（16px 邊距 + 400px 寬 + 16px 間隔），手機的面板從畫面 45% 的高度開始往下
const MOBILE_MAX_WIDTH = 720
const PANEL_SPACE = 432
const SHEET_RATIO = 0.55
const EDGE = 24

/** 被面板蓋住的範圍（px）：桌面是左邊，手機是下方。 */
function coveredArea() {
  if (window.innerWidth > MOBILE_MAX_WIDTH) return { left: PANEL_SPACE, bottom: 0 }
  return { left: 0, bottom: Math.round(window.innerHeight * SHEET_RATIO) }
}

const FILTERS = [
  ['all', '全部'],
  ['fireworks', KIND_LABELS.fireworks],
  ['maybe', KIND_LABELS.maybe],
]

// 煙火圖示用 SVG 畫：8 條放射線加中心點。不用 ✺ 這類字元，因為不是每台電腦的字型都有
const BURST_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><g stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
  [0, 45, 90, 135, 180, 225, 270, 315]
    .map((deg) => `<line x1="12" y1="5" x2="12" y2="8.5" transform="rotate(${deg} 12 12)"/>`)
    .join('') +
  '</g><circle cx="12" cy="12" r="1.8" fill="currentColor"/></svg>'

function markerIcon(event, status) {
  return L.divIcon({
    className: `fw-marker fw-marker--${event.kind} fw-marker--${status}`,
    html: BURST_SVG,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -16],
  })
}

// 彈出視窗用 DOM 組，文字一律放進 textContent：活動資料來自外部，不能當成 HTML
function popupContent(event, status) {
  const root = document.createElement('div')
  root.className = 'fw-popup'
  const add = (tag, className, text) => {
    const el = document.createElement(tag)
    el.className = className
    el.textContent = text
    root.append(el)
    return el
  }
  add('strong', 'fw-popup__name', event.name)
  add('div', 'fw-popup__meta', `${formatDateRange(event)}・${STATUS_LABELS[status]}・${KIND_LABELS[event.kind]}`)
  const place = formatPlace(event)
  if (place) add('div', 'fw-popup__place', place)
  if (event.organizer) add('div', 'fw-popup__place', event.organizer)
  const url = safeUrl(event.url)
  if (url) {
    const link = add('a', 'fw-popup__link', '活動網站')
    link.href = url
    link.target = '_blank'
    link.rel = 'noreferrer'
  }
  return root
}

/**
 * 煙火地圖：今年全臺的煙火相關活動（交通部觀光署開放資料）。
 *
 * - 地圖是整個網頁的背景：用 portal 放到 <body> 底下，固定佔滿畫面；活動清單留在查詢面板裡。
 * - 地圖只在掛上時建立一次，卸載時 map.remove()。
 * - 標記依篩選條件重畫；點清單裡的活動，地圖移過去並打開說明。
 * - 名稱有煙火的是「煙火大會」，只有說明提到的是「可能有煙火」，用不同樣式區分。
 */
export default function FireworksMap() {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const groupRef = useRef(null)
  const markersRef = useRef(new Map())
  const [state, setState] = useState({ status: 'loading', data: null })
  const [kind, setKind] = useState('all')
  const now = useMemo(() => new Date(), [])

  useEffect(() => {
    const { left, bottom } = coveredArea()
    // 縮放按鈕和資料來源放右上角：左邊（桌面）和下方（手機）會被面板蓋住
    const map = L.map(containerRef.current, {
      minZoom: 6,
      maxZoom: 15,
      zoomSnap: 0.5, // 手機畫面窄，允許半級縮放，全臺才不會縮得太小
      zoomControl: false,
      attributionControl: false,
    }).fitBounds(TAIWAN_BOUNDS, {
      paddingTopLeft: [left + EDGE, EDGE],
      paddingBottomRight: [EDGE, bottom + EDGE],
    })
    L.control.attribution({ position: 'topright' }).addTo(map)
    L.control.zoom({ position: 'topright' }).addTo(map)
    L.tileLayer(BASE_URL, { attribution: ATTRIBUTION, maxZoom: 15 }).addTo(map)
    mapRef.current = map
    groupRef.current = L.layerGroup().addTo(map)
    return () => {
      map.remove()
      mapRef.current = null
      groupRef.current = null
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchFireworks()
      .then((data) => !cancelled && setState({ status: 'success', data }))
      .catch(() => !cancelled && setState({ status: 'error', data: null }))
    return () => {
      cancelled = true
    }
  }, [])

  const events = useMemo(() => state.data?.events ?? [], [state.data])
  const visible = useMemo(() => filterEvents(events, kind), [events, kind])
  const counts = useMemo(() => countByKind(events), [events])

  useEffect(() => {
    const group = groupRef.current
    if (!group) return
    group.clearLayers()
    markersRef.current = new Map()
    for (const event of visible) {
      const status = eventStatus(event, now)
      const marker = L.marker([event.lat, event.lon], {
        icon: markerIcon(event, status),
        title: event.name,
        keyboard: true,
      })
        .bindPopup(() => popupContent(event, status))
        .addTo(group)
      markersRef.current.set(event.id, marker)
    }
  }, [visible, now])

  // 點清單：地圖飛到活動位置，讓標記落在「沒被面板蓋住」那一塊的中間
  function focus(event) {
    const map = mapRef.current
    if (!map) return
    const zoom = 11
    const { left, bottom } = coveredArea()
    const center = map.project([event.lat, event.lon], zoom).subtract([left / 2, -bottom / 2])
    map.flyTo(map.unproject(center, zoom), zoom, { duration: 0.6 })
    markersRef.current.get(event.id)?.openPopup()
    if (bottom) window.scrollTo({ top: 0, behavior: 'smooth' }) // 手機：捲回最上面，才看得到地圖
  }

  const year = state.data?.year

  return (
    <section className="fireworks card" aria-labelledby="fireworks-title">
      <div className="fireworks__header">
        <h2 id="fireworks-title" className="fireworks__title">
          <span className="fireworks__dot" aria-hidden="true" />
          煙火地圖
        </h2>
        <p className="fireworks__sub">
          {year ? `${year} 年` : '今年'}全臺的煙火活動，點活動看位置。資料來自交通部觀光署，每天更新
        </p>
      </div>

      {createPortal(
        <div
          ref={containerRef}
          className="map-bg"
          role="region"
          aria-label="煙火活動地圖，可以拖曳和縮放"
        />,
        document.body,
      )}

      {state.status === 'loading' && <p className="fireworks__note">載入活動中…</p>}
      {state.status === 'error' && (
        <p className="fireworks__note" role="alert">
          活動資料暫時無法取得，請稍後再試。
        </p>
      )}

      {state.status === 'success' && (
        <>
          <div className="fireworks__filters" role="group" aria-label="活動類型">
            {FILTERS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`fireworks__filter fireworks__filter--${key}`}
                aria-pressed={kind === key}
                onClick={() => setKind(key)}
              >
                <span>{label}</span>
                <span className="fireworks__count">{counts[key]}</span>
              </button>
            ))}
          </div>

          {visible.length === 0 ? (
            <p className="fireworks__note">今年目前沒有這類活動。</p>
          ) : (
            <ul className="fireworks__list">
              {visible.map((event) => {
                const status = eventStatus(event, now)
                return (
                  <li key={event.id} className={`fireworks__item fireworks__item--${status}`}>
                    <button type="button" onClick={() => focus(event)}>
                      <span className="fireworks__date">{formatDateRange(event)}</span>
                      <span className="fireworks__name">{event.name}</span>
                      <span className="fireworks__place">
                        {`${event.city ?? ''}${event.town ?? ''}`}
                      </span>
                      <span className={`fireworks__badge fireworks__badge--${status}`}>
                        {STATUS_LABELS[status]}
                      </span>
                      {event.kind === 'maybe' && (
                        <span className="fireworks__badge fireworks__badge--maybe">
                          {KIND_LABELS.maybe}
                        </span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
          <p className="fireworks__source">
            「可能有煙火」是活動說明裡提到煙火，不一定有煙火秀，出發前請看活動網站。
          </p>
        </>
      )}
    </section>
  )
}
