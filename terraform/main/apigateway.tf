resource "aws_apigatewayv2_api" "http" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
  description   = "WeatherCast public API"

  # 設定後，API Gateway 會自己回應瀏覽器的 OPTIONS 預檢請求並加上 CORS header，Lambda 不用處理
  dynamic "cors_configuration" {
    for_each = length(var.cors_allow_origins) > 0 ? [1] : []

    content {
      allow_origins = var.cors_allow_origins
      allow_methods = ["GET", "OPTIONS"]
      allow_headers = ["content-type"]
      max_age       = 3600
    }
  }
}

# Lambda proxy 整合：整個 HTTP 請求包成事件交給 Lambda，格式是 payload 2.0
resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = (var.lambda_timeout_seconds + 1) * 1000
}

# 只開放這三條路由，其他路徑由 API Gateway 直接回 404，不會執行 Lambda。
# 路徑帶 /api 前綴，之後前端透過 CloudFront 的 /api/* 轉發時，路徑不用改寫。
resource "aws_apigatewayv2_route" "routes" {
  for_each = toset(["GET /api/health", "GET /api/cities", "GET /api/weather"])

  api_id    = aws_apigatewayv2_api.http.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# API Gateway 自己的存取紀錄：每個請求一行，包含狀態碼、延遲和整合錯誤訊息，
# 遇到 502 時可以看出是 Lambda 出錯還是權限問題
resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${var.project_name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default" # 網址不帶 stage 名稱
  auto_deploy = true       # 路由或整合變更後自動生效，不用另外建 deployment

  # 費用防線：超過就回 429，不會執行 Lambda
  default_route_settings {
    throttling_rate_limit  = var.api_throttle_rate_limit
    throttling_burst_limit = var.api_throttle_burst_limit
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      latencyMs        = "$context.responseLatency"
      integrationError = "$context.integrationErrorMessage"
      lambdaStatus     = "$context.integration.status"
    })
  }
}

# 允許「這個 API」呼叫 Lambda；沒有這個，API Gateway 會回 500
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowInvokeFromHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
