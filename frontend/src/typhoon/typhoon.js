// 颱風圖層：把 /api/typhoons 的資料畫在衛星雲圖上，並產生文字說明。
//
// 這個檔案不 import Leaflet，由呼叫的人傳進來，測試時可以換成假的 L。

const DIRECTIONS = {
  N: '北', NNE: '北北東', NE: '東北', ENE: '東北東',
  E: '東', ESE: '東南東', SE: '東南', SSE: '南南東',
  S: '南', SSW: '南南西', SW: '西南', WSW: '西南西',
  W: '西', WNW: '西北西', NW: '西北', NNW: '北北西',
}

// 顏色：過去路徑白色實線、預測路徑黃色虛線、70% 機率範圍黃色半透明、暴風圈紅色
export const STYLE = {
  track: { color: '#ffffff', weight: 2, opacity: 0.9 },
  forecast: { color: '#ffd166', weight: 2, dashArray: '6 6' },
  probability: { color: '#ffd166', weight: 1, fillOpacity: 0.08 },
  galeCircle: { color: '#ff5d5d', weight: 1.5, fillOpacity: 0.12 },
  center: { radius: 6, color: '#ffffff', weight: 2, fillColor: '#ff5d5d', fillOpacity: 1 },
}

const KM = 1000 // L.circle 的半徑單位是公尺

const isNumber = (value) => typeof value === 'number' && Number.isFinite(value)
const latLng = (point) => [point.lat, point.lon]

/** 移動方向：WNW → 西北西；看不懂的代碼原樣顯示。 */
export function directionName(code) {
  return DIRECTIONS[code] ?? code ?? ''
}

/** 一行文字說明，地圖旁邊的清單和地圖上的提示框都用這個。 */
export function describeTyphoon(typhoon) {
  const { current } = typhoon
  const title = typhoon.name_en ? `${typhoon.name}（${typhoon.name_en}）` : typhoon.name
  const parts = [
    isNumber(current.max_wind_ms) && `近中心最大風速 ${current.max_wind_ms} m/s`,
    isNumber(current.pressure_hpa) && `中心氣壓 ${current.pressure_hpa} hPa`,
    isNumber(current.moving_speed_kmh) &&
      `向${directionName(current.moving_direction)} ${current.moving_speed_kmh} km/h`,
  ].filter(Boolean)
  return [title, ...parts].join('，')
}

/**
 * 在 group（L.layerGroup）裡畫出每個颱風：
 * 過去路徑、預測路徑（從現在位置連到各預測點）、70% 機率範圍、7 級風暴風圈、中心位置。
 */
export function drawTyphoons(L, group, typhoons) {
  group.clearLayers()
  for (const typhoon of typhoons) {
    const { current } = typhoon
    const forecast = typhoon.forecast.filter((p) => isNumber(p.lat) && isNumber(p.lon))

    if (typhoon.track.length > 1) {
      L.polyline(typhoon.track.map(latLng), STYLE.track).addTo(group)
    }
    if (forecast.length > 0) {
      L.polyline([latLng(current), ...forecast.map(latLng)], STYLE.forecast).addTo(group)
    }
    for (const point of forecast) {
      if (isNumber(point.radius_70pct_km)) {
        L.circle(latLng(point), { ...STYLE.probability, radius: point.radius_70pct_km * KM }).addTo(group)
      }
    }
    if (isNumber(current.radius_15ms_km)) {
      L.circle(latLng(current), { ...STYLE.galeCircle, radius: current.radius_15ms_km * KM }).addTo(group)
    }
    L.circleMarker(latLng(current), STYLE.center)
      .bindTooltip(describeTyphoon(typhoon), { direction: 'top' })
      .addTo(group)
  }
}
