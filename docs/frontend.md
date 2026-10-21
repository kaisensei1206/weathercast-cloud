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
      WeatherBackdrop.jsx   動態天氣背景（純裝飾）
    hooks/useWeatherScene.js        查詢狀態 → 背景場景
    hooks/usePrefersReducedMotion.js 系統的「減少動態效果」設定
    weather/scene.js        WMO 代碼分類、日夜判斷
    weather/effects.js      每種天氣的特效設定（顏色、強度）
    weather/particles.js    Canvas 雨、雪、星星
    App.jsx                 把以上組合起來
    index.css               樣式，含手機版、深色模式與天氣背景
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
- 正式環境：不設定，前端用相對路徑 `/api/...`，由 CloudFront 轉給 API Gateway（見第 5 節），所以網址不會寫死在任何元件裡，也不需要 CORS。

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

### 動態天氣背景

畫面後方會依目前天氣顯示對應的背景：晴天的陽光與光束、晴夜的月亮與星星、移動的雲、雨、雪、霧，以及雷雨偶爾的閃電。沒有使用圖片、影片或新套件。

**三層，各管一件事：**

| 檔案 | 輸入 → 輸出 | 說明 |
|---|---|---|
| `weather/scene.js` | API 回應 → 場景 `{ kind, intensity, cloudCover, night }` | 只看 `weather_code`（WMO 代碼），不看描述文字 |
| `weather/effects.js` | 場景 → 特效設定 | 所有顏色和強度都在這裡，調外觀只改這個檔案 |
| `components/WeatherBackdrop.jsx` | 特效設定 → 畫面 | CSS 畫天空、太陽、月亮、雲、霧；Canvas 畫雨、雪、星星 |

**天氣分類：**

| 類別 | WMO 代碼 | 特效 |
|---|---|---|
| `clear` | 0、1 | 白天：陽光、旋轉光束、淡淡的光斑。晚上：月亮、閃爍的星星 |
| `cloudy` | 2 | 白雲慢慢飄，陽光減弱 |
| `overcast` | 3 | 雲更厚、天空更灰，加一點霧，沒有陽光 |
| `drizzle` | 51–57 | 稀疏、短、慢、淡的雨絲，加薄霧 |
| `rain` | 61、63、66、80、81 | 中等密度的雨，依代碼強度調整 |
| `heavy-rain` | 65、67、82 | 密、長、快的雨，烏雲 |
| `storm` | 95、96、99 | 大雨、烏雲、7–15 秒隨機一次的柔和閃電 |
| `snow` | 71–77、85、86 | 大小、速度、透明度不同的雪花，左右搖擺；數量依降雪強度 |
| `fog` | 45、48 | 兩層半透明霧帶往相反方向飄 |
| `unknown` | 其他代碼、缺少代碼 | 中性的天空，沒有特效 |
| `idle` | 還沒查詢、查詢失敗 | 原本的背景色 |

**日夜判斷：** 後端沒有日夜欄位，所以用 `current.time`（臺灣當地時間）和臺灣中心點的經緯度，以 NOAA 的簡化公式算太陽高度角，低於 -0.833° 就是晚上。所有縣市的日出日落相差不到 15 分鐘，用一個點就夠了，也不需要修改 API。時間格式不對時當作白天。

**效能：**

- Canvas 引擎只在元件掛上時建立一次，換天氣只呼叫 `setConfig`，不重建 Canvas，也不重新註冊事件。
- 每一層的雨滴合併成一條路徑一次畫完；粒子數量依螢幕面積和 CPU 核心數調整（手機和低階裝置最少只有 25%）。
- 沒有雨、雪、星星時，動畫迴圈會停止；分頁切到背景時也會暫停。
- 雲和霧用 `transform: translateX` 移動，不用 `filter: blur`，交給 GPU 處理。
- 天氣的強度用 CSS 變數傳給樣式，不放進 React state；閃電只切換 class，不會重新渲染。

**切換天氣不閃爍：**

- 天空顏色用 `@property` 註冊成顏色型別，可以用 transition 漸變。
- 其他圖層用 opacity 淡入淡出，約 1.6 秒。
- 查詢下一個城市時保留上一個背景，等新資料回來才切換。查詢失敗則回到原本的背景色。

**閱讀與無障礙：**

- 背景是 `position: fixed`、`z-index: 0`、`pointer-events: none`、`aria-hidden`，不會擋住點擊，螢幕閱讀器也會略過。
- 內容在 `z-index: 1`，卡片維持原本的不透明底色，霧和雨都在卡片後面。
- 背景是天空時，標題和頁尾改成淺色字，並且：
  - 頂端有一層漸層加深；
  - 雲在最上方淡出；
  - 頁尾連結加半透明底。
- 用瀏覽器實測 16 種場景，標題文字後方最亮的像素和文字的對比都在 4.5:1 以上（WCAG AA）。
- 閃電最亮只到 30% 不透明度，一次閃光加一次較弱的餘光，間隔至少 7 秒，不會頻閃。
- 系統設定「減少動態效果」時：
  - 雲、霧、光束都停住；
  - 不閃電；
  - 雨和雪只畫一張靜態畫面，仍然看得出天氣。

## 4. 測試

`npm test` 共 119 個測試，全部是假資料，不會呼叫真的 API：

| 檔案 | 測什麼 |
|---|---|
| `api/weatherApi.test.js` | 網址組合與編碼；400、404（兩種）、502、504、500、非 JSON 回應各自歸到哪一類；網路失敗；用假時鐘測 10 秒逾時；空白與過長輸入不送出請求 |
| `App.test.jsx` | 載入中狀態與停用按鈕；天氣卡的每個欄位；從下拉選單查詢；縣市清單載入失敗時仍能輸入；四種錯誤畫面；錯誤後重新查詢；天氣卡的重新查詢 |
| `hooks/useWeather.test.js` | 較慢的舊回應不會蓋掉新結果；還沒查詢前按重新查詢不會出錯 |
| `components/WeatherCard.test.jsx` | 舊資料（`stale`）顯示提醒，以及資料來源是即時還是快取 |
| `weather/scene.test.js` | 每個 WMO 代碼的分類；未知、字串、`null` 代碼；夏至與冬至日出日落前後的日夜判斷；缺少資料不會出錯 |
| `weather/effects.test.js` | 每種天氣日夜都有不同天空；陰天比多雲重；毛毛雨到大雨、小雪到大雪的強度遞增；只有雷雨有閃電 |
| `weather/particles.test.js` | 依螢幕與 CPU 調整粒子數；只會有一個動畫迴圈；`destroy` 會停止迴圈並移除事件；減少動態效果時不跑動畫 |
| `components/WeatherBackdrop.test.jsx` | `aria-hidden`；換天氣更新 CSS 變數；沒有 Canvas 和 `matchMedia` 也不會出錯；閃電計時器在換天氣、卸載、開啟減少動態效果時都會清掉 |
| `hooks/useWeatherScene.test.js` | 載入中保留上一個背景；失敗回到預設；同一份資料回傳同一個物件 |
| `App.test.jsx`（新增一個） | 換城市時背景跟著換，查詢失敗回到預設 |

CI 的 `Frontend` job 在每個 PR 都會執行 `npm ci`、`npm test`、`npm run build`。

## 5. 部署到 S3 + CloudFront

Terraform 在 `terraform/main/frontend.tf`，部署步驟在 `.github/workflows/ci-cd.yml` 的 `deploy` job。合併到 main 後，CD 會自動打包前端、上傳到 S3、清除 CloudFront 快取，再做冒煙測試。

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

### 部署流程

`deploy` job 在原本的 Lambda 部署之後多做這幾步：

1. `npm ci && npm run build`，不設定 `VITE_API_BASE_URL`，前端用相對路徑 `/api`。
2. 上傳檔案：
   - 先傳 `dist/assets`，`Cache-Control: public,max-age=31536000,immutable`。Vite 打包出來的檔名含 hash，內容一變檔名就變，所以可以永久快取；`--delete` 清掉舊版的檔案。
   - 再傳其他檔案（`index.html`、`favicon.svg`），`Cache-Control: no-cache`。`index.html` 每次都要拿最新版，才會指到新的 assets。先傳 assets 再傳 `index.html`，使用者就不會拿到指向還不存在檔案的首頁。
3. `aws cloudfront create-invalidation --paths "/" "/index.html"`，讓 CloudFront 丟掉舊的首頁。
4. 冒煙測試：直接打 API Gateway 一次，再透過 CloudFront 網址打一次（`--frontend`），確認首頁是 WeatherCast 的 HTML，而且 `/api/*` 有轉給 API Gateway。

部署角色（`terraform/bootstrap/github_oidc.tf`）新增的權限：

| 權限 | 範圍 | 用途 |
|---|---|---|
| `s3:PutObject`、`s3:DeleteObject` | 只有 `weathercast-frontend-<帳號 ID>/*` | 上傳、刪除舊檔 |
| `s3:ListBucket`、`s3:GetBucket*` 等讀取 | 只有這個 bucket | `aws s3 sync` 比對檔案、`terraform plan` 讀設定 |
| `cloudfront:CreateInvalidation` | 這個帳號的 distribution | 清除快取。distribution ID 在主 stack 建立時才產生，bootstrap 無法事先指定 |
| `cloudfront:Get*`（3 個） | 這個帳號的 distribution 和 OAC | `terraform plan` 讀設定 |

部署角色仍然不能建立或刪除任何資源，也不能改 IAM。`scripts/check_plan.py` 不用改：新增 CloudFront 或 S3 屬於基礎設施變更，本來就應該由人在本機 apply。

### 已經部署過的環境怎麼升級

順序很重要：**先在本機 apply，再合併 PR。** 如果先合併，CD 的 plan 會看到 6 個新資源，`check_plan.py` 會擋下來，Deploy 會失敗（不會改到任何東西）。這時照下面做完，再到 GitHub Actions 手動重新執行（`workflow_dispatch`）即可。

在 PowerShell（記得先帶入 AWS 臨時憑證和 region）：

```powershell
cd E:\weathercast-cloud
git fetch
git checkout feat/frontend-hosting

# 1. 部署角色加權限：預期 Plan: 0 to add, 1 to change, 0 to destroy.（aws_iam_role_policy.github_deploy）
cd terraform\bootstrap
terraform plan "-out=bootstrap.tfplan"
terraform apply bootstrap.tfplan

# 2. 建立前端資源：預期 Plan: 6 to add, 0 to change, 0 to destroy.
cd ..\main
terraform plan "-out=main.tfplan"
terraform apply main.tfplan             # CloudFront 要 3 到 10 分鐘
terraform output -raw frontend_url      # 前端網址
```

第 2 步的 plan 應該只有 `cloudfront` 和 `s3_bucket` 開頭的 6 個資源，而且都是 `will be created`。出現其他資源要更新或刪除就先停下來。

apply 完成後合併 PR，CD 會上傳前端。部署成功後打開 `frontend_url` 就能看到網站。

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

- 用 CloudFront 預設的 `*.cloudfront.net` 網址，沒有自訂網域。
- 刪除主 stack 時，CloudFront 要先停用再刪除，可能要 10 分鐘以上。
- 測試用 jsdom 模擬瀏覽器，沒有真實瀏覽器的端對端測試。開發時有用真實瀏覽器（Chromium）搭配線上 API 手動確認過桌面版和手機版畫面。
- 沒有前端的覆蓋率報告。
- 動態背景的外觀、對比和快速切換是用真實瀏覽器（Chromium）手動跑腳本確認的，沒有放進 CI。
- 日夜判斷用臺灣中心點計算，日出日落前後幾分鐘可能和實際不同。
