# 颱風路徑（`GET /api/typhoons`）

資料來源是中央氣象署開放資料平臺的「颱風消息與警報－熱帶氣旋路徑」（資料集 `W-C0034-005`）。
後端整理成固定格式並快取，前端畫在衛星雲圖上（見 [frontend.md 的颱風路徑](frontend.md#颱風路徑)）。

## 1. API

`GET /api/typhoons`，沒有參數。

成功（200）。沒有颱風時 `typhoons` 是空陣列，這不是錯誤：

```json
{
  "typhoons": [
    {
      "name": "鳳凰",
      "name_en": "FUNG-WONG",
      "number": "26",
      "current": {
        "time": "2026-10-20T14:00:00+08:00", "lat": 19.0, "lon": 127.0,
        "max_wind_ms": 38.0, "max_gust_ms": 48.0, "pressure_hpa": 955.0,
        "moving_speed_kmh": 20.0, "moving_direction": "WNW", "radius_15ms_km": 250.0
      },
      "track": [{ "time": "2026-10-20T08:00:00+08:00", "lat": 18.5, "lon": 128.0 }],
      "forecast": [
        {
          "time": "2026-10-21T14:00:00+08:00", "lat": 20.5, "lon": 124.5, "tau_hours": 24.0,
          "max_wind_ms": 43.0, "max_gust_ms": 53.0, "pressure_hpa": 945.0, "radius_70pct_km": 120.0
        }
      ]
    }
  ],
  "meta": { "source": "upstream", "stale": false, "fetched_at": 1792148400, "provider": "cwa" }
}
```

| 狀態碼 | `error` | 什麼時候 |
|---|---|---|
| 503 | `typhoon_not_configured` | 沒有設定授權碼，或 SSM 裡找不到這個參數 |
| 504 | `upstream_timeout` | 氣象署超過 3 秒沒回應，而且沒有舊資料可用 |
| 502 | `upstream_error` | 氣象署回錯誤、格式不對、讀 SSM 失敗（例如權限不足），而且沒有舊資料可用 |

## 2. 設計決策

**授權碼放在 SSM Parameter Store，不放在 Terraform 或 Git。**
- 氣象署的資料要授權碼才能下載。授權碼是機密，不能出現在原始碼、Git，也不能出現在 Terraform state。
- 如果用 Terraform 的 `aws_ssm_parameter` 建立，值會寫進 state 檔，所以這個參數由人用 AWS CLI 建立，Terraform 只管「Lambda 可以讀它」。
- Lambda 的環境變數只有參數的「名稱」（`CWA_API_KEY_PARAM`），不是授權碼本身。在 Lambda 主控台看環境變數也看不到授權碼。
- 用 `SecureString`，以 AWS 管理的 `aws/ssm` KMS 金鑰加密。這把金鑰的政策已經允許帳號內有 `ssm:GetParameter` 權限的角色解密，所以 IAM 不用另外給 `kms:Decrypt`。
- 標準參數不收費，`GetParameter` 也不收費。

**最小權限。** Lambda 角色只多了一個動作：對 `parameter/weathercast/cwa-api-key` 這一個參數的 `ssm:GetParameter`。不能列出、修改或讀取其他參數。

**只讀一次 SSM。** 讀到的授權碼存在模組變數裡，同一個 Lambda 執行環境不會再呼叫 SSM。找不到參數時「不」記住結果，所以授權碼晚一點才存進 SSM 也不用重新部署。

**授權碼不會進 log。** 授權碼在網址的查詢參數裡，所以連線錯誤的訊息只寫狀態碼或錯誤類型，不寫網址。有測試檢查錯誤訊息和 log 裡沒有授權碼。

**快取和天氣共用同一張 DynamoDB 表。**
- 用固定的 key `typhoons:cwa`，和城市 ID 不會撞名。
- 流程和天氣一樣：10 分鐘內用快取；超過就問氣象署；氣象署失敗時回 24 小時內的舊資料並標示 `stale`；DynamoDB 故障時直接問氣象署。
- 氣象署每 3 到 6 小時才更新一次颱風路徑，10 分鐘快取讓大部分請求不用呼叫氣象署，也不容易用完授權碼的呼叫額度。

**後端先整理格式。**
- 氣象署的座標是 `"經度,緯度"` 字串，數字也是字串；後端轉成數字，前端不用知道氣象署的格式。
- 預報點只有「發布時間 + tau 小時」，後端算好實際時間。
- 只有一筆資料時，氣象署的 JSON 可能是物件而不是陣列，兩種都接受。
- 座標壞掉的點直接略過；一個颱風完全沒有有效座標就整個略過。整體結構不對（`success` 不是 `true`、沒有 `records`）才算錯誤。

**逾時。** 最壞情況：讀 SSM 2 次 × 2 秒 + 讀 DynamoDB 1 秒 + 氣象署 3 秒 + 寫 DynamoDB 1 秒 = 9 秒，仍在 Lambda 的 10 秒逾時內；而且 SSM 只有冷啟動後第一次會讀。

## 3. 設定授權碼（只需要做一次）

1. 到 [氣象資料開放平臺](https://opendata.cwa.gov.tw/) 註冊並登入，在「取得授權碼」頁面複製授權碼。
2. 在 PowerShell 登入 AWS（`aws login`），然後存進 SSM。授權碼只出現在你自己的終端機：

   ```powershell
   aws ssm put-parameter --name /weathercast/cwa-api-key --type SecureString --region ap-northeast-1 --value "你的授權碼"
   ```

3. 確認存好了。這個指令只列出名稱和類型，不會顯示授權碼：

   ```powershell
   aws ssm describe-parameters --region ap-northeast-1 --parameter-filters "Key=Name,Values=/weathercast/cwa-api-key"
   ```

之後要換授權碼，在第 2 步加上 `--overwrite`。已經在執行的 Lambda 記住的是舊的值，要等執行環境重新啟動（冷啟動）才會讀新的；想立刻生效，可以重新部署 Lambda。

本機執行後端時，可以改用環境變數 `CWA_API_KEY` 直接提供授權碼，不需要 SSM。

## 4. 部署（已經部署過的環境）

這次改了 Terraform（新的路由、Lambda 環境變數、IAM 權限），`check_plan.py` 只允許 CD 更新 Lambda 程式碼，所以要先在本機 apply 再合併：

```powershell
cd E:\weathercast-cloud
git fetch
git checkout feat/typhoon-track
cd terraform\main
terraform plan "-out=main.tfplan"    # 前端（PR #11）已經 apply 過時，預期 Plan: 1 to add, 2 to change, 0 to destroy.
terraform apply main.tfplan
```

- 新增的 1 個是 `aws_apigatewayv2_route.routes["GET /api/typhoons"]`。
- 更新的 2 個是 `aws_lambda_function.api`（環境變數和程式碼）和 `aws_iam_role_policy.lambda`（讀 SSM 的權限）。

apply 之後確認：

```powershell
$api = terraform output -raw api_endpoint
curl.exe -s -i "$api/api/typhoons"
```

已經存好授權碼時是 200；還沒存是 503 `typhoon_not_configured`，網站其他功能不受影響。

## 5. 測試

全部用假資料，不會呼叫氣象署或真的 AWS：

| 檔案 | 測什麼 |
|---|---|
| `tests/test_typhoon_client.py` | 授權碼：環境變數優先、從 SSM 讀（moto 模擬）、只讀一次、找不到時停用且不記住、權限不足和連線失敗歸為上游錯誤。呼叫：網址、逾時、各種連線錯誤，而且錯誤訊息沒有授權碼。格式：欄位轉換、預報時間、熱帶性低氣壓沒有名字、單筆物件、壞掉的座標、缺欄位、沒有颱風、錯誤的結構 |
| `tests/test_typhoon_service.py` | 沒有快取、新鮮快取、過期重查、氣象署失敗時回舊資料、超過 24 小時不回、DynamoDB 故障時改問氣象署、和天氣共用表但 key 不同 |
| `tests/test_handler.py`（新增） | 200、503、504、502，log 裡沒有授權碼，第二次請求用快取 |

## 6. 目前限制

- **氣象署回應的欄位名稱還沒用真實資料核對過。** 測試用的範例（`tests/fakes.py` 的 `SAMPLE_CWA`）是依開放資料文件整理的。要等授權碼存好之後，用真實回應確認一次；欄位不同時只需要改 `typhoon_client.py` 的整理函式和範例。
- 只顯示氣象署有發布路徑的熱帶氣旋，通常是可能影響臺灣附近的颱風，不是全球所有颱風。
- 颱風圖層不跟著衛星雲圖的時間軸切換。
