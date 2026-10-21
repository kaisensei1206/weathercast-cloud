# 煙火活動（`GET /api/fireworks`）

資料來源是交通部觀光署的「觀光資訊資料庫－活動」（[政府資料開放平臺 7778](https://data.gov.tw/dataset/7778)）。
後端挑出和煙火有關的活動並快取，前端畫成地圖（見 [frontend.md 的煙火地圖](frontend.md#煙火地圖)）。

## 1. API

`GET /api/fireworks`，沒有參數。回傳今年（臺灣時間）的活動，依開始時間排序：

```json
{
  "year": 2026,
  "events": [
    {
      "id": "Event_376540000A_006236",
      "name": "2026成功鎮花火之夜",
      "kind": "fireworks",
      "start": "2026-02-16T21:00:00+08:00",
      "end": "2026-02-16T23:59:59+08:00",
      "city": "臺東縣", "town": "成功鎮", "address": "海濱公園",
      "lat": 23.10404, "lon": 121.38497,
      "url": null, "image": "https://tour.taitung.gov.tw/image/54819/640x480", "organizer": null
    }
  ],
  "meta": { "source": "upstream", "stale": false, "fetched_at": 1792148400, "provider": "taiwan-tourism" }
}
```

- `kind`：`fireworks` 是名稱有「煙火、烟火、花火、焰火」；`maybe` 是只有說明提到。
- 沒有活動時 `events` 是空陣列，不是錯誤。

| 狀態碼 | `error` | 什麼時候 |
|---|---|---|
| 504 | `upstream_timeout` | 觀光署超過 5 秒沒回應，而且沒有舊資料可用 |
| 502 | `upstream_error` | 觀光署回錯誤、檔案格式不對，而且沒有舊資料可用 |

## 2. 資料來源（2026-10-21 實測）

- 下載網址：`https://media.taiwan.net.tw/XMLReleaseAll_public/v2.0/Zh_tw/Event-json.zip`。不需要金鑰，每天更新。
- zip 約 0.5 MB，裡面的 `EventList.json` 約 2.8 MB（UTF-8 有 BOM），共 1,161 筆活動。
- 結構是 `Events[]`。用到的欄位：`EventID`、`EventName`、`Description`、`StartDateTime`、`EndDateTime`（ISO 8601，含 `+08:00`）、`PositionLat`、`PositionLon`（數字）、`PostalAddress`、`WebsiteURL`、`Images`、`Organizations`、`EventStatus`。
- 2026 年名稱有煙火的活動只有 2 個（成功鎮花火之夜、日月潭花火音樂嘉年華）；只有說明提到煙火的另有十幾筆。澎湖花火節、國慶焰火沒有登錄在這份資料裡。
- 另一份「歷史活動」資料只更新到 2024 年，所以沒有使用。

## 3. 設計決策

**只用官方資料。** 不手動維護活動清單，資料每天自動更新，來源可以查證。缺點是觀光署沒有登錄的活動不會出現，所以畫面上寫明資料來源。

**分成「煙火大會」和「可能有煙火」。** 觀光署的資料沒有「煙火」分類，只能用文字判斷。名稱有煙火的幾乎一定是煙火活動；只有說明提到的，可能是音樂節最後放煙火，也可能只是順帶提到，所以分開標示，讓使用者自己判斷。

**後端先整理格式。** 前端拿到的是固定欄位的小清單，不用懂觀光署的格式：
- 沒有名稱、開始時間或座標的活動略過；已取消（`EventCancelled`）的略過。
- 同一個活動登錄兩次（名稱只差空白、開始日期相同）只留一筆。例如日月潭花火音樂嘉年華在資料裡出現兩次。

**外部檔案不可全信。**
- 下載大小上限 10 MB；解壓縮前先看 zip 標示的檔案大小，超過 50 MB 就拒絕，不會真的解開（防 zip bomb）。
- 只讀 `EventList.json` 一個檔案，不把 zip 解到磁碟。
- 前端把活動文字當純文字顯示，網址只接受 http、https。

**快取。**
- 和天氣共用同一張 DynamoDB 表，key 是 `fireworks:tourism`，和城市 ID 不會撞名。
- 流程和天氣一樣：10 分鐘內用快取；超過就重新下載；下載失敗時回 24 小時內的舊資料並標示 `stale`；DynamoDB 故障時直接下載。
- 快取存所有年份的煙火活動，回應時才依臺灣時間挑出今年的。這樣跨年那一刻不會拿到去年的結果。
- 一筆快取只有幾十筆活動，遠小於 DynamoDB 單筆 400 KB 的上限。

**「今年」用臺灣時間。** 臺灣沒有日光節約時間，固定用 UTC+8，不依賴 Lambda 環境的時區資料庫。跨年活動（12/31 開始、1/1 結束）兩年都算。

**逾時。** 下載給 5 秒（檔案比天氣 API 大）。最壞情況：讀 DynamoDB 1 秒 + 下載 5 秒 + 寫 DynamoDB 1 秒 = 7 秒，仍在 Lambda 的 10 秒逾時內。

**不用新的 AWS 權限。** 只是 Lambda 對外下載公開檔案，和呼叫 Open-Meteo 一樣，IAM 不用改。

## 4. 部署（已經部署過的環境）

這次多了一條 API Gateway 路由。`check_plan.py` 只允許 CD 更新 Lambda 程式碼，所以要先在本機 apply 再合併：

```powershell
cd E:\weathercast-cloud
git fetch
git checkout feat/fireworks-map
cd terraform\main
terraform plan "-out=main.tfplan"    # 前端（PR #11）已經 apply 過時，預期 Plan: 1 to add, 1 to change, 0 to destroy.
terraform apply main.tfplan
```

- 新增的 1 個是 `aws_apigatewayv2_route.routes["GET /api/fireworks"]`。
- 更新的 1 個是 `aws_lambda_function.api`（程式碼和說明）。

apply 之後確認：

```powershell
$api = terraform output -raw api_endpoint
curl.exe -s "$api/api/fireworks"
```

## 5. 測試

全部用假資料，不會連到觀光署或真的 AWS。zip 在測試裡現場組出來，結構和真實檔案相同（含 BOM）。

| 檔案 | 測什麼 |
|---|---|
| `tests/test_fireworks_client.py` | 下載網址與逾時；各種連線錯誤；下載太大、解壓後太大、不是 zip、少了檔案、JSON 壞掉、編碼錯誤；煙火關鍵字分類；缺欄位、取消、座標錯誤的活動略過；重複活動只留一筆；依時間排序 |
| `tests/test_fireworks_service.py` | 「今年」用臺灣時間；跨年活動兩年都算；只回傳今年；快取新鮮時不下載；跨年後同一份快取改回傳新的一年；下載失敗回舊資料；超過 24 小時不回；DynamoDB 故障時改為直接下載 |
| `tests/test_handler.py`（新增） | 200、504、502，第二次請求用快取 |

## 6. 目前限制

- 只有觀光署登錄的活動。很多煙火活動（例如澎湖花火節、國慶焰火）沒有登錄，地圖上就不會出現。
- 「可能有煙火」是用文字判斷的，有些活動其實沒有煙火秀。
- 長時間的活動（例如日月潭花火音樂嘉年華 9/12–11/14）資料裡只有整段期間，沒有每一場煙火的日期。
