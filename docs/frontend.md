# 前端：React + Vite

一個頁面的天氣查詢介面，在 `frontend/`。可以輸入城市名稱，或從 22 縣市清單選擇，查詢後顯示城市、溫度、體感溫度、濕度、降雨量、風速和天氣代碼。

## 1. 本機開發

需要 Node.js 22.13 以上（`frontend/.nvmrc`）。Vite 8 和 Vitest 5 不支援更舊的版本。

```powershell
cd E:\weathercast-cloud\frontend
node --version                       # v22.13 以上
npm ci                               # 依 package-lock.json 安裝，版本和 CI 相同
Copy-Item .env.example .env.local    # 再把 <api-id> 換成實際的 API Gateway 網址
npm run dev                          # http://localhost:5173
```

`.env.local` 的內容：

```text
VITE_API_BASE_URL=https://pecxa1tq55.execute-api.ap-northeast-1.amazonaws.com
```

- 開發伺服器固定用 5173 port（`strictPort`）。API Gateway 的 CORS 只允許 `http://localhost:5173`，換成別的 port 瀏覽器就會擋下請求，畫面顯示「網路連線失敗」。
- `.env.local` 被 `.gitignore` 排除，不會提交。

其他指令：

| 指令 | 用途 |
|---|---|
| `npm test` | 執行一次所有測試（Vitest + jsdom，不連網路） |
| `npm run test:watch` | 改程式時自動重跑測試 |
| `npm run build` | 打包到 `frontend/dist/`，這就是要上傳到 S3 的檔案 |
| `npm run preview` | 在本機用打包後的檔案開網站，確認 build 結果 |

## 2. 結構

```
frontend/
  index.html
  vite.config.js            開發伺服器 port、測試環境設定
  .env.example              VITE_API_BASE_URL 範例
  src/
    api/config.js           唯一讀取 VITE_API_BASE_URL 的地方
    api/weatherApi.js       呼叫後端：組網址、逾時、把失敗整理成 ApiError
    hooks/useWeather.js     查詢狀態：idle → loading → success / error
    hooks/useCities.js      載入 22 縣市清單
    components/
      SearchForm.jsx        城市輸入框、縣市下拉選單、查詢按鈕
      WeatherCard.jsx       天氣卡
      StatusMessage.jsx     載入中與錯誤訊息
    App.jsx                 把以上組合起來
    index.css               樣式，含手機版與深色模式
```

資料流向：

```
SearchForm ──onSearch(city)──► useWeather ──► weatherApi.fetchWeather ──► GET /api/weather
                                    │
             WeatherCard / StatusMessage ◄── status、data、error
```

## 3. 設計決策

**元件和 API 呼叫分開。** 只有 `src/api/` 會呼叫 `fetch`。元件不知道網址、HTTP 狀態碼和逾時，只看 `ApiError.kind` 決定顯示哪一種訊息。好處是：

- 改 API 不用改元件。
- 元件測試只要把 API 模組換成假的，不需要模擬 HTTP。

**錯誤分成五類：**

| `kind` | 什麼情況 | 畫面 |
|---|---|---|
| `invalid_input` | 沒輸入、超過 50 字，或後端回 400 | 輸入有誤 |
| `not_found` | 後端回 404 `city_not_found` | 找不到這個城市，並提示支援的縣市 |
| `network` | `fetch` 失敗：斷網、DNS、CORS 被擋 | 網路連線失敗 |
| `timeout` | 10 秒沒有回應 | 連線逾時 |
| `server` | 5xx、其他 404、回應不是 JSON | 伺服器發生錯誤 |

- 後端的 502、504 都歸在 `server`，畫面上顯示後端回傳的說明，例如「氣象資料來源暫時無法使用」。
- 每種錯誤都有「重新查詢」按鈕；天氣卡上也有，用來更新資料。

**逾時 10 秒。** 瀏覽器的 `fetch` 本身沒有逾時，伺服器不回應就會一直等。這裡用 `AbortController` 在 10 秒後中斷請求。後端呼叫 Open-Meteo 最多等 3 秒，再加上 Lambda 冷啟動的時間，10 秒已經很寬鬆。

**只採用最後一次查詢的結果。** 每次查詢都有編號，回應回來時，如果已經有更新的查詢，就丟掉舊的結果。查詢中按鈕會停用，所以一般操作碰不到這種情況，這是額外的保險。

**城市清單向後端要。** 下拉選單的 22 縣市來自 `GET /api/cities`，前端不再存一份，新增縣市只要改後端。清單載入失敗時下拉選單會隱藏，輸入框照樣可以用。

**`VITE_API_BASE_URL` 只在 `config.js` 讀取。**

- 本機開發：設成 API Gateway 網址，靠 CORS 跨網域呼叫。
- 正式環境：不設定，前端用相對路徑 `/api/...`，由 CloudFront 轉給 API Gateway（見第 5 節），所以網址不會寫死在任何元件裡。

**前端沒有任何機密。** `VITE_` 開頭的環境變數會被直接打包進 JavaScript，任何人打開瀏覽器開發者工具都看得到，所以只能放公開資訊，例如 API 網址。這個專案的 API 本來就是公開的唯讀 API，不需要金鑰。

**刻意不加的東西：**

- 只有一個頁面，所以不用 router。
- 只有一個查詢狀態，所以不用 Redux 之類的狀態管理。
- 不用 UI 框架，樣式只有一個約 300 行的 CSS。
- 用 JavaScript 而不是 TypeScript，讓專案容易看懂。要加型別檢查，可以之後再改成 TypeScript。

**Responsive 與無障礙：**

- 寬度 480px 以下時，輸入框和按鈕改成上下排列，按鈕高度至少 44px，方便手指點擊。
- 天氣細節用 CSS grid 自動換行。
- 跟著系統設定切換深色模式。
- 載入中用 `role="status"`、錯誤用 `role="alert"`，螢幕閱讀器會念出來。

## 4. 測試

`npm test` 共 34 個測試，全部是假資料，不會呼叫真的 API：

| 檔案 | 測什麼 |
|---|---|
| `api/weatherApi.test.js` | 網址組合與編碼；400、404（兩種）、502、504、500、非 JSON 回應各自歸到哪一類；網路失敗；用假時鐘測 10 秒逾時；空白與過長輸入不送出請求 |
| `App.test.jsx` | 載入中狀態與停用按鈕；天氣卡的每個欄位；從下拉選單查詢；縣市清單載入失敗時仍能輸入；四種錯誤畫面；錯誤後重新查詢；天氣卡的重新查詢 |
| `hooks/useWeather.test.js` | 較慢的舊回應不會蓋掉新結果；還沒查詢前按重新查詢不會出錯 |
| `components/WeatherCard.test.jsx` | 舊資料（`stale`）顯示提醒，以及資料來源是即時還是快取 |

CI 的 `Frontend` job 在每個 PR 都會執行 `npm ci`、`npm test`、`npm run build`。

## 5. 部署到 S3 + CloudFront：Terraform 設計建議（尚未實作）

這一節是設計建議，還沒有寫成 Terraform，也沒有建立任何資源。

```
瀏覽器 ──HTTPS──► CloudFront
                   ├─ /api/*  ──► API Gateway（現有）
                   └─ 其他    ──► S3 私有 bucket（frontend/dist）
                                   只接受這個 CloudFront 透過 OAC 讀取
```

### 新增的資源（主 stack，約 6 個）

| 資源 | 設定重點 |
|---|---|
| `aws_s3_bucket` | 名稱例如 `weathercast-frontend-<帳號 ID>`，不開 static website hosting |
| `aws_s3_bucket_public_access_block` | 四項全部 `true`，bucket 完全不公開 |
| `aws_s3_bucket_server_side_encryption_configuration` | SSE-S3（AES256）；OAC 搭配 SSE-KMS 要另外給 KMS 權限，靜態網站不需要 |
| `aws_cloudfront_origin_access_control` | `signing_behavior = "always"`、`signing_protocol = "sigv4"`、類型 `s3` |
| `aws_cloudfront_distribution` | 兩個 origin、兩個 behavior，見下方 |
| `aws_s3_bucket_policy` | 只允許 CloudFront 服務讀取，而且限定這一個 distribution |

bucket policy 的重點是 `AWS:SourceArn` 條件。沒有這個條件，帳號裡任何一個 CloudFront distribution 都能讀這個 bucket：

```json
{
  "Effect": "Allow",
  "Principal": { "Service": "cloudfront.amazonaws.com" },
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::weathercast-frontend-<帳號 ID>/*",
  "Condition": {
    "StringEquals": { "AWS:SourceArn": "arn:aws:cloudfront::<帳號 ID>:distribution/<distribution ID>" }
  }
}
```

### CloudFront 的設定

| 項目 | 建議 | 原因 |
|---|---|---|
| 預設 behavior → S3 | managed policy `CachingOptimized`；`viewer_protocol_policy = "redirect-to-https"` | 靜態檔可以快取 |
| `/api/*` behavior → API Gateway | `CachingDisabled` + origin request policy `AllViewerExceptHostHeader`；只允許 `GET`、`HEAD`、`OPTIONS` | 天氣快取已經由 DynamoDB 處理，CloudFront 再快取一次會讓「10 分鐘內新鮮」的行為變得難以預測。不能轉送 `Host` header，否則 API Gateway 會找不到對應的 API |
| API Gateway origin | `domain_name` 用 `api_endpoint` 去掉 `https://`；`origin_protocol_policy = "https-only"` | HTTP API 只接受 HTTPS |
| `default_root_object` | `index.html` | 開網站根目錄時回傳首頁 |
| SPA 錯誤頁 | **不要**設定「403/404 改回 `index.html`」 | 這個前端只有一頁、沒有 router，不需要這個設定。CloudFront 的錯誤頁設定對整個 distribution 都有效，會把 API 的 404 `city_not_found` JSON 換成 HTML，前端就無法分辨「找不到城市」 |
| `price_class` | `PriceClass_200` | 包含亞洲的節點，台灣使用者比較快；`PriceClass_All` 多出的南美、澳洲節點用不到 |
| 憑證 | CloudFront 預設的 `*.cloudfront.net` 憑證 | 不用另外買網域 |

改成同網域之後，正式環境不再需要 CORS。`cors_allow_origins` 可以維持只有 `http://localhost:5173`，給本機開發使用。

### 部署流程的變更

1. `terraform apply`（在本機）建立 bucket 和 distribution，output 加上 `frontend_bucket`、`cloudfront_distribution_id`、`cloudfront_url`。
2. 在 `ci-cd.yml` 的 `deploy` job 加三個步驟：
   1. `npm ci && npm run build`，不設定 `VITE_API_BASE_URL`。
   2. 上傳檔案：
      - 先傳 `aws s3 sync dist/assets s3://<bucket>/assets --delete --cache-control "public,max-age=31536000,immutable"`。Vite 打包出來的檔名含 hash，內容一變檔名就變，所以可以永久快取；`--delete` 清掉舊版的檔案。
      - 再傳 `aws s3 cp dist/index.html s3://<bucket>/index.html --cache-control "no-cache"`。`index.html` 每次都要拿最新版，才會指到新的 assets。先傳 assets 再傳 `index.html`，使用者就不會拿到指向還不存在檔案的首頁。
      - `favicon.svg` 用 `aws s3 cp` 另外上傳。
   3. `aws cloudfront create-invalidation --paths "/index.html"`。
3. 部署角色加上最小權限（寫在 bootstrap 的 `github_oidc.tf`）：
   - 對 `weathercast-frontend-*` bucket：`s3:ListBucket`、`s3:PutObject`、`s3:DeleteObject`。
   - 對這一個 distribution：`cloudfront:CreateInvalidation`。
   - `terraform plan` 要讀新資源，所以也要加上 `s3:GetBucket*`、`cloudfront:GetDistribution`、`cloudfront:GetOriginAccessControl`、`cloudfront:ListTagsForResource` 等讀取權限。
4. `scripts/check_plan.py` 不用改：新增 CloudFront 或 S3 屬於基礎設施變更，本來就應該由人在本機 apply。
5. 冒煙測試加一個檢查：`GET <cloudfront_url>/api/health` 回 200，確認 CloudFront 轉發 `/api/*` 正常。

### 費用

| 項目 | 免費額度（每月） | 這個專案的用量 |
|---|---|---|
| CloudFront | 1 TB 流量、1,000 萬次請求（永久免費方案） | 遠低於額度 |
| S3 | 前 12 個月 5 GB；之後約每 GB 0.025 美元 | 打包結果約 230 KB |
| CloudFront invalidation | 每月前 1,000 個路徑免費 | 每次部署 1 個路徑 |

預期每月幾乎是 0 美元，現有的 5 美元預算提醒仍然有效。

### 為什麼不直接公開 bucket

- S3 static website hosting 只支援 HTTP，還要關掉 Block Public Access，bucket 裡的每個檔案都能被直接下載。
- 用 OAC 時，bucket 保持私有，只有這個 CloudFront 能讀。使用者一律透過 HTTPS 連線，還能享有 CloudFront 的快取和 DDoS 基本防護（AWS Shield Standard）。

## 6. 目前限制

- 前端還沒部署到 AWS，只能在本機執行。上面的 S3 + CloudFront 是設計建議。
- 測試用 jsdom 模擬瀏覽器，沒有真實瀏覽器的端對端測試。開發時有用真實瀏覽器（Chromium）搭配線上 API 手動確認過桌面版和手機版畫面。
- 沒有前端的覆蓋率報告。
