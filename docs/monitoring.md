# 監控、告警與流量限制

這份文件回答三個問題：

1. API 是公開的，怎麼避免被大量呼叫造成費用？
2. 快取（DynamoDB）壞掉時，怎麼避免每個請求都打到外部 API？
3. 服務出錯時，誰會知道？

Terraform 在 `terraform/main/monitoring.tf`（告警）和 `terraform/main/apigateway.tf`（節流），程式在 `backend/src/weather_cache.py`。

## 1. 流量限制

### 現在有什麼

| 防線 | 設定 | 作用 |
|---|---|---|
| 全部路由的節流 | 每秒 10 次、瞬間 20 次 | 超過的請求由 API Gateway 直接回 429，不會執行 Lambda |
| `/api/fireworks` 的節流 | 每秒 2 次、瞬間 5 次 | 這條路由的回應最大，快取過期時還要下載觀光署整個 zip，所以另外調低 |
| 請求量突增告警 | 5 分鐘 1,500 次 | 平常展示用每天幾百次。達到節流上限一半就寄信，可以在費用累積前發現 |
| AWS Budget | 每月 5 美元 | 實際費用到 80%、預估費用到 100% 時寄信（用 AWS CLI 建立，不在 Terraform 裡） |
| 快取 | 每個城市 10 分鐘 | 重複的查詢不會再呼叫上游 |

**節流不是每個使用者的配額。** 每秒 10 次是所有人共用的上限：有人大量呼叫時，其他使用者也會收到 429。它保護的是費用和上游，不是公平性。

### 最壞情況的費用

有人一直打到節流上限時，一個月最多約 2,600 萬次請求（10 × 86,400 × 30）。費用大約是：

```text
請求數 × (API Gateway 每次單價 + Lambda 每次請求單價 + Lambda 執行時間 × 記憶體單價) + CloudWatch Logs 寫入量
```

大部分請求會命中快取，Lambda 執行時間很短，粗估在數十美元等級。實際金額請用 [AWS Pricing Calculator](https://calculator.aws/) 估算。想把上限壓得更低，調小 `api_throttle_rate_limit` 就好。

### 評估過但沒有做的

| 做法 | 為什麼沒做 | 什麼時候該做 |
|---|---|---|
| AWS WAF（依 IP 限速） | 每月至少 5 美元的 Web ACL 加上每條規則 1 美元，已經超過整個專案的預算。而且 WAF 不能直接掛在 HTTP API 上，只能掛在 CloudFront；別人直接呼叫 API Gateway 的網址就能繞過 | 有真實使用者、需要依 IP 限速或擋惡意流量時，掛在 CloudFront 上，並讓 API 只接受來自 CloudFront 的請求 |
| API Key 與使用量方案 | HTTP API 沒有使用量方案（只有 REST API 有）。API Key 會出現在前端程式碼裡，任何人都看得到，不能拿來辨識身分 | 要讓第三方開發者使用，需要依使用者計費或限量時，搭配身分驗證（例如 Cognito）一起做 |
| Lambda reserved concurrency | 新的 AWS 帳號同時執行上限可能只有 10。保留一部分會讓帳號剩餘的額度不足，Terraform 會直接失敗 | 帳號的同時執行上限提高之後，可以設成 5，作為 API Gateway 節流之外的第二道上限 |

## 2. 快取故障時保護上游

原本的設計是 fail-open：DynamoDB 失敗時照樣呼叫 Open-Meteo，服務不會中斷。問題是快取持續故障時，每個請求都會打到上游。現在多了兩層保護：

- **記憶體備援**：讀寫 DynamoDB 成功的資料，也存一份在 Lambda 的記憶體裡。DynamoDB 讀不到時改用記憶體的資料，新鮮期和保留期的判斷不變。
- **斷路器**：DynamoDB 失敗一次後，30 秒內直接跳過 DynamoDB，請求不用每次多等 1 到 2 秒的逾時。

結果：快取故障時，同一個 Lambda 執行環境裡每個城市每 10 分鐘最多呼叫 Open-Meteo 一次，和正常時一樣。測試 `test_dynamodb_outage_does_not_send_every_request_upstream` 驗證了 9 分鐘內查 10 次只呼叫上游 1 次。

**為什麼不重試 DynamoDB？** 重試會讓每個請求等更久，而且 DynamoDB 真的故障時，重試只會增加負擔。斷路器的作用剛好相反：失敗後先停一段時間。

**整體逾時**：Open-Meteo 3 秒、觀光署 5 秒、DynamoDB 連線和讀取各 1 秒、Lambda 10 秒。最壞情況仍在 Lambda 逾時內，不會讓請求一直掛著。

**限制**：

- 記憶體是每個 Lambda 執行環境各自一份。同時有 N 個執行環境時，上游呼叫最多是正常時的 N 倍。
- 冷啟動時記憶體是空的。
- 這是比較簡單的「失敗後暫停固定時間」，不是依失敗率開關的完整斷路器。

## 3. 告警

### 通知方式

所有告警送到 SNS topic `weathercast-alerts`，再寄 email。告警觸發時寄一封，恢復正常時再寄一封。

Email 訂閱**不寫在 Terraform 裡**，部署後用 AWS CLI 加上（見第 4 節）。這樣 email 不會出現在 Git、GitHub Actions 的設定或 Terraform state。

### 7 個告警

每個告警看 5 分鐘的資料，一個週期達到門檻就通知。沒有資料時視為正常，所以沒人使用的時段不會誤報。

| 告警 | 指標 | 門檻 | 為什麼是這個門檻 |
|---|---|---|---|
| `weathercast-lambda-errors` | Lambda `Errors` | ≥ 1 | 程式的錯誤都會被接住並回傳 4xx/5xx，Lambda 層級的錯誤代表程式例外、逾時或記憶體不足，出現一次就要看 |
| `weathercast-lambda-throttles` | Lambda `Throttles` | ≥ 1 | 正常流量不應該發生，出現代表帳號的同時執行上限不夠 |
| `weathercast-lambda-duration` | Lambda `Duration` 最大值 | ≥ 8,000 ms | 逾時 10 秒的 80%。上游變慢時，會在真正逾時前先通知 |
| `weathercast-api-5xx` | API Gateway `5xx` | ≥ 5 | 偶爾一次上游逾時（504）不用叫人，連續發生才代表服務有問題 |
| `weathercast-api-traffic-spike` | API Gateway `Count` | ≥ 1,500 | 見第 1 節 |
| `weathercast-upstream-failures` | 自訂 `UpstreamFailures` | ≥ 3 | Open-Meteo 或觀光署逾時、錯誤，包含改回傳過期快取的情況。上游有問題但使用者還沒看到錯誤時就先知道 |
| `weathercast-dynamodb-errors` | 自訂 `DynamoDBErrors` | ≥ 1 | 快取故障時服務仍然正常，只看 5xx 不會發現，所以要另外監控 |

7 個標準告警在 CloudWatch 每月 10 個的免費額度內。

**服務目標**：這是展示用的專案，沒有正式的 SLO。門檻是依「出現就代表有東西壞了」（Lambda 錯誤、DynamoDB 錯誤）和「偶發可以接受、連續發生才通知」（5xx、上游錯誤）兩種情況設定的。如果有正式的可用性目標，例如 99.9%，應該改成依錯誤率設定告警。

### 從 log 轉出的指標

程式印出的 JSON log（`backend/src/logger.py`）用 metric filter 轉成 `WeatherCast` namespace 下的指標：

| 指標 | 來源 log |
|---|---|
| `UpstreamFailures` | `upstream_timeout`、`upstream_error`、`serving_stale_cache` |
| `DynamoDBErrors` | `dynamodb_error`（斷路器打開期間跳過的呼叫不算） |
| `CacheHits` | `weather_ok` 或 `fireworks_ok`，而且 `source` 是 `cache` |
| `CacheMisses` | `weather_ok` 或 `fireworks_ok`，而且 `source` 是 `upstream` |

快取命中率可以在 CloudWatch 主控台用 metric math 算：`CacheHits / (CacheHits + CacheMisses)`。命中率沒有設告警，因為流量很少時這個比例的變化很大，容易誤報。

## 4. 部署

告警會新增資源，也要改部署角色的權限，所以 CD 不會自動部署。合併 PR 之前，在本機依序執行：

1. **bootstrap**：部署角色要能讀新的告警資源，CI 的 `terraform plan` 才不會失敗。

   ```powershell
   cd E:\weathercast-cloud\terraform\bootstrap
   terraform plan "-out=bootstrap.tfplan"   # 預期：0 to add, 1 to change（部署角色的 policy）
   terraform apply bootstrap.tfplan
   ```

2. **主 stack**：

   ```powershell
   cd E:\weathercast-cloud\terraform\main
   terraform plan "-out=main.tfplan"   # 預期：12 to add, 2 to change（stage 的節流、Lambda 的程式碼）
   terraform apply main.tfplan
   ```

3. **訂閱告警 email**：把 `you@example.com` 換成你的 email。

   ```powershell
   $topic = terraform output -raw alerts_topic_arn
   aws sns subscribe --topic-arn $topic --protocol email --notification-endpoint you@example.com
   ```

   AWS 會寄一封確認信，點信裡的連結後才會開始收到告警。確認狀態：

   ```powershell
   aws sns list-subscriptions-by-topic --topic-arn $topic --query "Subscriptions[].SubscriptionArn"
   ```

   還沒確認時會顯示 `PendingConfirmation`，確認後會是一串 ARN。

4. **測試告警**：手動把一個告警設成 ALARM，應該會收到 email。下一次評估時（最多 5 分鐘）會自動回到 OK，再收到一封恢復通知。

   ```powershell
   aws cloudwatch set-alarm-state --alarm-name weathercast-lambda-errors --state-value ALARM --state-reason "manual test"
   ```

5. 合併 PR。CI 的 plan 會顯示沒有變更，或只有 Lambda 程式碼，CD 照常部署。

## 5. 目前限制

- 節流是全部使用者共用，沒有依 IP 或使用者區分（見第 1 節的 WAF）。
- 告警只寄 email，沒有接 Slack 或值班系統。
- SNS topic 沒有用 KMS 加密：CloudWatch 告警無法使用 AWS 管理的 `aws/sns` 金鑰，自建金鑰每月 1 美元。告警內容只有指標名稱和數值，沒有使用者資料。
- 沒有 CloudWatch Dashboard；要看趨勢時直接在主控台查指標。
