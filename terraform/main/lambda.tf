locals {
  function_name = "${var.project_name}-api"
}

# 打包 backend/src 成 zip。後端只用標準函式庫和 Lambda 內建的 boto3，
# 所以不需要另外安裝套件；tests/test_packaging.py 會檢查這件事。
# zip 的根目錄就是 backend/src，所以 handler 是 "handler.lambda_handler"。
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../backend/src"
  output_path = "${path.module}/build/lambda.zip"
  excludes    = ["__pycache__", "**/__pycache__/**", "**/*.pyc"]

  # 固定檔案權限：Windows 和 Linux 打包出來的 zip 才會一樣，不會每次 plan 都顯示要更新
  output_file_mode = "0644"
}

resource "aws_cloudwatch_log_group" "lambda" {
  # Lambda 固定寫到這個名稱的 log group；先建好才能設定保留天數
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name = local.function_name
  description   = "WeatherCast API: /api/health, /api/cities, /api/weather, /api/fireworks"
  role          = aws_iam_role.lambda.arn

  runtime       = "python3.12"
  architectures = ["arm64"] # Graviton 比 x86 便宜約 20%；純 Python 沒有原生套件，不受架構影響
  handler       = "handler.lambda_handler"
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout_seconds

  # Lambda 程式碼由 Terraform 負責部署：內容改變時 hash 會變，plan 就會顯示要更新
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      CACHE_TABLE          = aws_dynamodb_table.cache.name
      CACHE_FRESH_SECONDS  = tostring(var.cache_fresh_seconds)
      CACHE_RETAIN_SECONDS = tostring(var.cache_retain_seconds)
    }
  }

  # 先有 log group 和權限，Lambda 第一次執行時才寫得了 log
  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda,
  ]
}
