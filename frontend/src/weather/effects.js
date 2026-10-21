// 每種場景要顯示哪些特效、強度多少。所有數值集中在這裡，調整外觀只改這個檔案。
// 特效半透明地疊在背景地圖上，所以沒有天空顏色、太陽和月亮，只留下會「蓋在地面上」的天氣。
//
// 回傳的欄位：
//   shade      把地圖壓暗的程度（0–1）：下雨、晚上比較暗，晴天白天是 0
//   clouds     雲層的不透明度（0–1）
//   cloudShade 雲的顏色：light 白雲、dark 烏雲
//   fog        霧氣（0–1）
//   precipitation  { type: 'rain' | 'snow', density, speed, length, opacity, wind }；沒有降水是 null
//   lightning  是否偶爾閃電

// 白天各種天氣的壓暗程度；晚上再多加 NIGHT_SHADE，讓地圖看起來像夜晚
const SHADE = {
  clear: 0,
  cloudy: 0.03,
  overcast: 0.06,
  drizzle: 0.06,
  rain: 0.1,
  'heavy-rain': 0.15,
  storm: 0.2,
  snow: 0.08,
  fog: 0.04,
  unknown: 0.03,
}
// 最暗（雷雨的晚上）是 0.35：標記和彈出視窗也在特效下面，不能壓得太暗
const NIGHT_SHADE = 0.15

const NONE = {
  shade: 0,
  clouds: 0,
  cloudShade: 'light',
  fog: 0,
  precipitation: null,
  lightning: false,
}

function rain({ density, speed, length, opacity, wind }) {
  return { type: 'rain', density, speed, length, opacity, wind }
}

/** 依場景計算特效設定。純函式，同樣的場景一定得到同樣的結果。 */
export function getEffects(scene) {
  const { kind, intensity = 0, cloudCover = 0, night = false } = scene ?? {}
  if (!Object.hasOwn(SHADE, kind)) return { ...NONE }

  const shade = SHADE[kind] + (night ? NIGHT_SHADE : 0)
  const effects = { ...NONE, shade, clouds: cloudCover }

  switch (kind) {
    case 'overcast':
      effects.fog = 0.15
      break
    case 'drizzle':
      effects.fog = 0.2
      effects.precipitation = rain({
        density: 0.15 + 0.25 * intensity,
        speed: 0.55,
        length: 0.45,
        opacity: 0.35,
        wind: 0.05,
      })
      break
    case 'rain':
      effects.fog = 0.2
      effects.precipitation = rain({
        density: 0.35 + 0.4 * intensity,
        speed: 0.8,
        length: 0.75,
        opacity: 0.45,
        wind: 0.12,
      })
      break
    case 'heavy-rain':
      effects.cloudShade = 'dark'
      effects.fog = 0.3
      effects.precipitation = rain({ density: 1, speed: 1, length: 1, opacity: 0.55, wind: 0.2 })
      break
    case 'storm':
      effects.cloudShade = 'dark'
      effects.fog = 0.2
      effects.lightning = true
      effects.precipitation = rain({
        density: 0.7 + 0.3 * intensity,
        speed: 1,
        length: 1,
        opacity: 0.5,
        wind: 0.25,
      })
      break
    case 'snow':
      effects.fog = 0.15
      effects.precipitation = { type: 'snow', density: 0.25 + 0.75 * intensity, speed: 0.5, opacity: 0.85 }
      break
    case 'fog':
      effects.fog = 0.45 + 0.4 * intensity
      break
    default:
      break
  }
  return effects
}
