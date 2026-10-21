# CI/CD：GitHub Actions 測試與自動部署

workflow 在 [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml)，一個檔案、三個 job：

| Job | 什麼時候跑 | 做什麼 | AWS 權限 |
|---|---|---|---|
| `test` | 每個 PR、每次 push 到 main | ruff、pytest、`terraform fmt`、`terraform validate` | 沒有 |
| `frontend` | 每個 PR、每次 push 到 main | `npm ci`、`npm test`、`npm run build` | 沒有 |
| `deploy` | push 到 main（合併 PR）或手動觸發，而且 `test`、`frontend` 都通過 | OIDC 登入 AWS → plan → 檢查 plan → apply → 上傳前端 → 清除 CloudFront 快取 → 冒煙測試 | 只能更新既有的 Lambda、上傳到既有的前端 bucket、清除快取 |

```
PR ──► test ──► (不部署)

main ─► test + frontend ──► deploy: OIDC 換臨時憑證 ─► terraform plan ─► check_plan.py ─► terraform apply
          │                                                                │
       失敗就停                                             改到 Lambda 以外的資源就停
                                   ─► build 前端 ─► s3 sync ─► CloudFront invalidation ─► smoke_test.py
                                                                                              │
                                                                       API 或網站不正常就標示失敗
```

## 1. 每個 job 做什麼

### test

1. `actions/checkout`、`actions/setup-python`（Python 3.12，快取 pip）。
2. `pip install -r requirements-dev.txt`。
3. `ruff check`、`ruff format --check`：程式風格與常見錯誤。
4. `pytest --cov`：全部單元測試，不連網路也不連 AWS（`tests/conftest.py` 擋掉對外連線，DynamoDB 用 moto 模擬），並印出 `backend/src` 的覆蓋率報告。
5. `terraform fmt -check -recursive terraform`。
6. 對 bootstrap 和 main 各跑 `terraform init -backend=false` 和 `terraform validate`。`-backend=false` 只下載 provider，不讀 S3 上的 state，所以不需要 AWS 憑證。

`test` 只有 `contents: read`，不能拿 OIDC token，PR（包含來自 fork 的 PR）裡的程式碼碰不到 AWS。

### deploy

- `needs: [test, frontend]`：任何一個失敗，`deploy` 不會執行。
- `if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'`：PR 永遠不部署。
- `concurrency: deploy-production`、`cancel-in-progress: false`：連續合併兩個 PR 時，第二次部署排隊，不會中斷正在 apply 的那一次（中斷 apply 可能留下鎖或不完整的 state）。

步驟：

| 步驟 | 說明 |
|---|---|
| Configure AWS credentials (OIDC) | `aws-actions/configure-aws-credentials` 向 GitHub 要一個 OIDC token，用它呼叫 `sts:AssumeRoleWithWebIdentity` 換成 `weathercast-github-deploy` 角色的臨時憑證（最長 1 小時） |
| Terraform init | 用 repo 變數 `TF_STATE_BUCKET` 連到 S3 上的主 stack state |
| Terraform plan | `archive_file` 重新打包 `backend/src`，和線上版本比較 |
| Check plan only updates Lambda | `scripts/check_plan.py` 讀 `terraform show -json` 的結果，只允許「沒有變更」或「`aws_lambda_function.api` update」，其他變更一律停止 |
| Terraform apply | 套用剛剛檢查過的那份 plan 檔，不會重新計算 |
| Read Terraform outputs | 讀出 API 網址、前端網址、bucket 名稱和 distribution ID，給後面的步驟用 |
| Build frontend | `npm ci && npm run build`，不設定 `VITE_API_BASE_URL`，前端用相對路徑 `/api` |
| Upload frontend to S3 | 先傳 `assets/`（永久快取），再傳 `index.html` 等其他檔案（`no-cache`），見 [frontend.md](frontend.md) 第 5 節 |
| Invalidate CloudFront cache | 清除 `/` 和 `/index.html` 的快取 |
| Smoke test | `scripts/smoke_test.py` 打 `/api/health` 和 `/api/weather?city=Tainan`，檢查狀態碼和內容；再對 CloudFront 網址加上 `--frontend` 跑一次，多檢查首頁。失敗會每 3 秒重試，最多 5 次 |

成功或失敗會顯示在 GitHub 的 Actions 頁面、PR 合併後的 commit 旁（綠勾或紅叉），GitHub 也會寄 email 通知 workflow 失敗。

## 2. Terraform 和 CI 怎麼分工

| 誰 | 負責 | 用什麼權限 |
|---|---|---|
| 人，在本機 | 建立、修改、刪除基礎設施（加資料表、改 IAM、改路由、bootstrap） | 自己的 AWS 登入（`aws login`） |
| GitHub Actions | 把 main 上的新版程式碼部署到「已經存在」的 Lambda，把前端上傳到「已經存在」的 bucket | OIDC 部署角色，只能更新那一個 Lambda、寫入那一個 bucket、清除 CloudFront 快取 |

兩邊都用 `terraform apply`，不用 `aws lambda update-function-code`。只有 Terraform 會改 Lambda 的程式碼，state 裡記的 hash 就永遠和線上一致，不會發生「CI 上傳新版、下次本機 apply 又蓋回舊版」的 State Drift（見 [infrastructure.md](infrastructure.md)）。

合併的 PR 如果改到 Lambda 以外的資源，`check_plan.py` 會印出：

```text
[ok] update           aws_lambda_function.api
[BLOCKED] create           aws_dynamodb_table.extra
Plan changes infrastructure, not just Lambda code. Review and apply it locally (docs/deployment.md), then re-run this workflow.
```

這時在本機看過 plan 後 apply（[deployment.md](deployment.md) 第 3 到 5 節），再到 Actions 頁面手動重跑 workflow。就算沒有這個檢查，部署角色也沒有建立或修改其他資源的權限，apply 會在 AWS 那邊被拒絕；`check_plan.py` 是讓它在 apply 之前就停下來，訊息也比 AccessDenied 清楚。

## 3. OIDC 與部署角色

### 為什麼用 OIDC，不用 Access Key

Access Key 是長期有效的密碼，存進 GitHub Secrets 之後要定期輪替，外洩了在撤銷前一直能用。OIDC 的做法是：

1. workflow 執行時，GitHub 簽發一個短效的 JWT，裡面寫著是哪個 repo、哪個分支、哪個事件。
2. AWS 用 GitHub 的公鑰驗證簽章，再檢查角色的信任政策（trust policy）。
3. 通過就發一組臨時憑證，最長 1 小時後失效。

GitHub 和 repo 裡都沒有任何 AWS 金鑰。repo 變數 `AWS_DEPLOY_ROLE_ARN` 只是角色名稱，不是秘密，外人知道它也沒辦法使用。

### 信任政策

由 `terraform/bootstrap/github_oidc.tf` 產生，apply 後的實際內容：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Principal": {
        "Federated": "arn:aws:iam::<帳號 ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:kaisensei1206@134856648/weathercast-cloud@1421996870:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

- `aud`：token 必須是發給 AWS STS 的。
- `sub`：只接受這個 repo 的 main 分支。PR 的 token 是 `repo:...:pull_request`，其他分支是 `ref:refs/heads/<分支>`，fork 的 repo 名稱不同，全部會被拒絕。
- 用 `StringEquals`，不用 `StringLike` 加萬用字元，避免 `repo:kaisensei1206/*` 這類寫法讓同一個帳號下的其他 repo 也能使用。
- `@134856648`、`@1421996870` 是帳號和 repo 的數字 ID。這個 repo 開啟了 GitHub 的 immutable subject，token 的 `sub` 會同時帶名稱和 ID。名稱可以改、刪掉後也能被別人用同名重建，ID 不會；所以就算有人註冊了同名帳號或 repo，也拿不到這個角色。ID 寫在 bootstrap 的 `github_owner_id`、`github_repository_id` 變數，查詢方式：`gh api repos/kaisensei1206/weathercast-cloud --jq '.owner.id, .id'`。
- repo 用的是哪一種 `sub` 格式可以這樣查：`gh api repos/kaisensei1206/weathercast-cloud/actions/oidc/customization/sub`。`use_immutable_subject` 是 `true` 時就是上面的格式。

所以「只能從 main 部署」有兩道保護：workflow 的 `if` 條件，以及 AWS 這邊的 `sub` 條件。就算有人改了 workflow 讓 PR 也跑 deploy，AWS 仍會拒絕。

### 部署角色的權限

| 類別 | 動作 | 範圍 | 為什麼需要 |
|---|---|---|---|
| state | `s3:ListBucket` | state bucket，限 `weathercast/main.tfstate*` 前綴 | Terraform 讀取與鎖定 state |
| state | `s3:GetObject`、`PutObject`、`DeleteObject` | `weathercast/main.tfstate*` | 讀寫主 stack 的 state，以及建立、刪除 `.tflock` 鎖檔 |
| 讀取 | `lambda:Get*`、`lambda:List*` | `weathercast-api` | plan 時重新讀取 Lambda 現況 |
| 讀取 | `dynamodb:Describe*`、`ListTagsOfResource` | `weathercast-cache` | 同上 |
| 讀取 | `iam:GetRole`、`GetRolePolicy`、`ListRolePolicies`、`ListAttachedRolePolicies` | `weathercast-lambda` 角色 | 同上 |
| 讀取 | `logs:DescribeLogGroups`、`ListTagsForResource`、`ListTagsLogGroup` | 兩個 log group | 同上；`DescribeLogGroups` 是列表 API，只能授權到 `log-group:*` |
| 讀取 | `apigateway:GET` | 這個 Region 的 `/apis/*` | 同上；API ID 是主 stack 建立時才產生，無法事先寫死 |
| 讀取 | `s3:GetBucket*`、`ListBucket` 等 | `weathercast-frontend-<帳號 ID>` | plan 讀 bucket 設定；`aws s3 sync` 比對檔案 |
| 讀取 | `cloudfront:GetDistribution`、`GetDistributionConfig`、`ListTagsForResource`、`GetOriginAccessControl` | 這個帳號的 distribution 和 OAC | plan 讀設定；ID 是主 stack 建立時才產生 |
| 讀取 | `sns:GetTopicAttributes`、`ListTagsForResource` | `weathercast-alerts` topic | plan 讀告警的 SNS topic |
| 讀取 | `cloudwatch:DescribeAlarms` | `*` | plan 讀告警；列表型 API，不一定支援指定單一告警 |
| 讀取 | `cloudwatch:ListTagsForResource` | `weathercast-*` 告警 | 同上 |
| 讀取 | `logs:DescribeMetricFilters` | Lambda 的 log group | plan 讀 log 轉指標的設定 |
| **寫入** | `lambda:UpdateFunctionCode`、`UpdateFunctionConfiguration` | `weathercast-api` | 更新後端程式碼 |
| **寫入** | `s3:PutObject`、`DeleteObject` | `weathercast-frontend-<帳號 ID>/*` | 上傳前端、刪除舊檔 |
| **寫入** | `cloudfront:CreateInvalidation` | 這個帳號的 distribution | 部署後清除快取 |

刻意沒有的權限：

- 任何建立或刪除資源的權限：`Create*`、`Delete*`、`Put*` 只有上表列出的幾個例外（state 檔和前端檔案的 `PutObject`、`DeleteObject`，以及 `CreateInvalidation`），都是寫入「檔案」或「快取」，不是建立 AWS 資源。
- `iam:PassRole`、任何 IAM 寫入：不能把 Lambda 換成權限更大的角色，也不能替自己加權限。
- bootstrap 的 state：它只存在你的電腦上，CI 碰不到 bootstrap，所以也不能改自己的信任政策或權限。

`tests/test_ci_cd.py` 會檢查 policy 裡的寫入動作正好是上表那五個，S3 寫入只能落在 state 的 key 和前端 bucket，沒有 `*` 和 `iam:PassRole`；也檢查 workflow 沒有使用 secrets 或 Access Key、只有 `deploy` 能要 OIDC token、`deploy` 必須等 `test` 和 `frontend` 而且不在 PR 執行、先傳 assets 再傳 `index.html`。

讀取權限是照 Terraform AWS provider 刷新這些資源時會呼叫的 API 整理的，還沒在真實 AWS 跑過。第一次部署如果出現 `AccessDenied`，錯誤訊息會寫出缺少的動作，補進 `github_oidc.tf` 後在本機 apply bootstrap 即可。

## 4. 第一次啟用

以下在你的電腦上執行（PowerShell，`E:\weathercast-cloud`），需要先用 `aws login` 登入。

### 4-1 確認帳號裡還沒有 GitHub 的 OIDC 身分提供者

一個帳號對同一個網址只能有一個 OIDC 身分提供者。

```powershell
aws iam list-open-id-connect-providers
```

- 輸出是 `"OpenIDConnectProviderList": []`，或沒有 `token.actions.githubusercontent.com`：直接進行 4-2。
- 已經有了（例如以前其他專案建過）：先匯入，Terraform 才不會嘗試再建一個：
  `terraform import aws_iam_openid_connect_provider.github arn:aws:iam::<帳號 ID>:oidc-provider/token.actions.githubusercontent.com`

### 4-2 在 bootstrap 建立 OIDC 與部署角色

```powershell
cd E:\weathercast-cloud\terraform\bootstrap
aws configure export-credentials --format powershell --region ap-northeast-1 | Invoke-Expression
terraform init
terraform plan "-out=bootstrap.tfplan"
```

預期 `Plan: 3 to add, 0 to change, 0 to destroy.`，三行是：

```text
  # aws_iam_openid_connect_provider.github will be created
  # aws_iam_role.github_deploy will be created
  # aws_iam_role_policy.github_deploy will be created
```

S3 bucket 那 6 個資源不應該出現任何變更。確認後：

```powershell
terraform apply bootstrap.tfplan
terraform output -raw github_deploy_role_arn
```

這 3 個 IAM 資源不收費。apply 後記得再備份一次 `terraform\bootstrap\terraform.tfstate`。

### 4-3 設定 GitHub repo 變數

用的是 **Variables**，不是 Secrets：兩個值都不是機密，放在 Variables 可以在 log 裡看到實際值，方便除錯。

**用 GitHub CLI：**

```powershell
cd E:\weathercast-cloud
gh variable set AWS_DEPLOY_ROLE_ARN --body (terraform "-chdir=terraform\bootstrap" output -raw github_deploy_role_arn)
gh variable set TF_STATE_BUCKET --body (terraform "-chdir=terraform\bootstrap" output -raw state_bucket)
gh variable list
```

**或用網頁：** repo → Settings → Secrets and variables → Actions → **Variables** 分頁 → New repository variable，新增：

| 名稱 | 值 |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<帳號 ID>:role/weathercast-github-deploy` |
| `TF_STATE_BUCKET` | `weathercast-tfstate-<帳號 ID>` |

### 4-4 合併 PR，觀察第一次部署

1. 合併這個 PR。合併本身就是一次 push 到 main，會觸發 workflow。
2. repo → Actions → CI/CD → 最新一次執行。
3. `Test` 通過後 `Deploy` 開始。這次合併沒有改 `backend/src`，預期 `check_plan.py` 印出 `No changes.`，apply 也沒有變更，接著冒煙測試通過。
4. 之後要再手動部署：Actions → CI/CD → Run workflow → 選 main。

如果 `Deploy` 失敗：

| 失敗的步驟 | 常見原因 |
|---|---|
| Configure AWS credentials | `Not authorized to perform sts:AssumeRoleWithWebIdentity`：repo 變數的角色 ARN 打錯、bootstrap 還沒 apply、不是從 main 執行，或 token 的 `sub` 和信任政策不符。CloudTrail 的 `AssumeRoleWithWebIdentity` 事件裡，`userIdentity.userName` 就是 GitHub 實際送出的 `sub`，可以直接比對 |
| Terraform init | `TF_STATE_BUCKET` 沒設或打錯 |
| Terraform plan | `AccessDenied`：部署角色少了某個讀取權限，見第 3 節最後一段 |
| Check plan | 這次合併改到 Lambda 以外的資源，見第 2 節 |
| Smoke test | 新版程式碼有問題；看 CloudWatch Logs（[deployment.md](deployment.md) 第 8 節），修好後再合併一次，或在本機 apply 上一版 |

### 4-5 （repo 公開後）保護 main 分支

GitHub 免費方案的私人 repo 不能設定 branch protection 和 Environment 保護規則。repo 改成公開後建議加上：

- Settings → Branches（或 Rules → Rulesets）→ 保護 `main`：
  - Require a pull request before merging
  - Require status checks to pass，選 `Test`
  - Block force pushes
- 這樣沒通過 CI 的 PR 無法合併，main 上的程式碼一定通過過測試。

在那之前，「CI 失敗就不部署」由 `needs: test` 保證：main 上的 `test` 失敗時，`deploy` 不會執行。

## 5. 目前限制

- 部署角色的讀取權限還沒有在真實 AWS 驗證過，第一次執行可能需要補權限。
- 沒有使用 GitHub Environment（需要人工核准的部署）：免費方案的私人 repo 不支援。repo 公開後，可以建立 `production` Environment、設定 required reviewers，並把信任政策的 `sub` 改成 `repo:kaisensei1206@134856648/weathercast-cloud@1421996870:environment:production`。
- 冒煙測試只打兩個端點，確認服務活著、能回傳台南的天氣，不是完整的整合測試。
- 冒煙測試失敗時不會自動回滾，需要人決定是修正後重新部署，還是 revert 那次合併。
- 第三方 action 用版本 tag（`@v5`），沒有釘到 commit SHA。要更嚴格可以改用 SHA，並用 Dependabot 更新。
