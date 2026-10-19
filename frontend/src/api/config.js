// 後端網址只在這裡讀取一次，元件不直接碰環境變數。
//
// VITE_API_BASE_URL 留空時使用相對路徑 /api/...：
//   正式環境由 CloudFront 把 /api/* 轉給 API Gateway，前後端同網域，不需要 CORS。
// 本機開發在 .env.local 設成 API Gateway 網址（見 .env.example）。
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')

// 後端呼叫 Open-Meteo 最多 3 秒，加上 Lambda 冷啟動，10 秒還沒回應就當作逾時
export const REQUEST_TIMEOUT_MS = 10_000
