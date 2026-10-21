import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchTyphoons } from '../api/weatherApi.js'
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion.js'
import { MAX_NATIVE_ZOOM, formatTaipeiTime, frameTimes, tileUrl } from '../satellite/frames.js'
import { describeTyphoon, drawTyphoons } from '../typhoon/typhoon.js'

const TAIWAN = [23.7, 121]
const LEGEND = [
  ['track', '過去路徑'],
  ['forecast', '預測路徑'],
  ['probability', '70% 機率範圍'],
  ['gale', '7 級風暴風圈'],
]
const FRAME_MS = 600 // 每張停留時間
const LAST_FRAME_MS = 1800 // 播到最新一張多停一下，看得出「這是現在」

// CARTO 的深色底圖：衛星雲圖用 mix-blend-mode: screen 疊上去，
// 紅外線影像裡暗的部分（地面、海面）會消失，只留下亮的雲
const BASE_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
const ATTRIBUTION =
  'Imagery: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> / JMA Himawari · ' +
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

/**
 * 衛星雲圖：最近 2 小時、每 10 分鐘一張的紅外線影像，可以播放、暫停、拖曳時間軸。
 *
 * - 地圖和圖層只在掛上時建立一次；每個時間點一個圖層，全部先載入，
 *   播放時只切換透明度，不會一張一張重新下載而閃爍。
 * - 卸載時移除地圖（含所有事件）和計時器。
 * - 偏好減少動態效果時不自動播放，停在最新一張。
 * - 颱風路徑來自 /api/typhoons（中央氣象署），畫在雲圖上面、不跟著時間軸切換。
 *   取得失敗（例如還沒設定授權碼）就只顯示雲圖，不顯示錯誤。
 */
export default function SatelliteMap() {
  const times = useMemo(() => frameTimes(), [])
  const reducedMotion = usePrefersReducedMotion()
  const containerRef = useRef(null)
  const layersRef = useRef([])
  const typhoonGroupRef = useRef(null)
  const [frame, setFrame] = useState(times.length - 1)
  const [playing, setPlaying] = useState(!reducedMotion)
  const [typhoons, setTyphoons] = useState(null) // null：還沒取得或取得失敗

  useEffect(() => {
    const map = L.map(containerRef.current, {
      center: TAIWAN,
      zoom: 4,
      minZoom: 3,
      maxZoom: 7,
      scrollWheelZoom: false, // 捲動頁面時不要意外縮放地圖
      worldCopyJump: true,
    })
    L.tileLayer(BASE_URL, { attribution: ATTRIBUTION, subdomains: 'abcd', maxZoom: 7 }).addTo(map)

    layersRef.current = times.map((time, i) =>
      L.tileLayer(tileUrl(time), {
        maxNativeZoom: MAX_NATIVE_ZOOM, // 超過就放大原圖，不再要更細的圖磚
        maxZoom: 7,
        opacity: i === times.length - 1 ? 1 : 0,
        className: 'satellite__frame',
      }).addTo(map),
    )

    // 颱風圖層在所有雲圖圖層之後加入，所以畫在雲的上面
    typhoonGroupRef.current = L.layerGroup().addTo(map)

    return () => {
      map.remove()
      layersRef.current = []
      typhoonGroupRef.current = null
    }
  }, [times])

  useEffect(() => {
    let cancelled = false
    fetchTyphoons()
      .then((list) => !cancelled && setTyphoons(list))
      .catch(() => !cancelled && setTyphoons(null))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (typhoons && typhoonGroupRef.current) drawTyphoons(L, typhoonGroupRef.current, typhoons)
  }, [typhoons])

  // 只切換透明度
  useEffect(() => {
    layersRef.current.forEach((layer, i) => layer.setOpacity(i === frame ? 1 : 0))
  }, [frame])

  useEffect(() => {
    if (reducedMotion) setPlaying(false)
  }, [reducedMotion])

  useEffect(() => {
    if (!playing) return undefined
    const delay = frame === times.length - 1 ? LAST_FRAME_MS : FRAME_MS
    const timer = setTimeout(() => setFrame((f) => (f + 1) % times.length), delay)
    return () => clearTimeout(timer)
  }, [playing, frame, times.length])

  return (
    <section className="satellite card" aria-labelledby="satellite-title">
      <div className="satellite__header">
        <div>
          <h2 id="satellite-title" className="satellite__title">
            衛星雲圖
          </h2>
          <p className="satellite__sub">向日葵衛星紅外線影像，每 10 分鐘一張，共 2 小時（衛星資料約晚 1 小時公開）</p>
        </div>
        <button
          type="button"
          className="button"
          onClick={() => setPlaying((p) => !p)}
          aria-pressed={playing}
        >
          {playing ? '暫停' : '播放'}
        </button>
      </div>

      <div
        ref={containerRef}
        className="satellite__map"
        role="region"
        aria-label="衛星雲圖地圖，可以拖曳和縮放"
      />

      <div className="satellite__timeline">
        <input
          type="range"
          min="0"
          max={times.length - 1}
          value={frame}
          onChange={(e) => {
            setPlaying(false)
            setFrame(Number(e.target.value))
          }}
          aria-label="影像時間"
          aria-valuetext={formatTaipeiTime(times[frame])}
        />
        {/* 不用 <output>：它預設是 live region，播放時螢幕閱讀器會每 0.6 秒念一次 */}
        <span className="satellite__time">{formatTaipeiTime(times[frame])}（臺灣時間）</span>
      </div>

      {typhoons && (
        <div className="typhoons">
          <h3 className="typhoons__title">颱風動態（中央氣象署）</h3>
          {typhoons.length === 0 ? (
            <p className="typhoons__empty">目前沒有颱風或熱帶性低氣壓。</p>
          ) : (
            <>
              <ul className="typhoons__list">
                {typhoons.map((t) => (
                  <li key={`${t.number ?? ''}-${t.name}`}>{describeTyphoon(t)}</li>
                ))}
              </ul>
              <ul className="typhoons__legend" aria-label="圖例">
                {LEGEND.map(([key, label]) => (
                  <li key={key}>
                    <span className={`typhoons__key typhoons__key--${key}`} aria-hidden="true" />
                    {label}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}
