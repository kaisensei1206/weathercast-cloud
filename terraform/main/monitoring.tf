# 告警：服務出問題時寄信通知，而不是等使用者發現。
#
# 告警送到一個 SNS topic。Email 訂閱不寫在 Terraform 裡，部署後用 AWS CLI 加（docs/monitoring.md），
# 這樣 email 不會進到 Git、GitHub 設定或 Terraform state。
#
# 7 個告警都在 CloudWatch 免費額度（10 個標準告警）內。沒有資料時視為正常（notBreaching），
# 沒人使用的時段不會一直處於 INSUFFICIENT_DATA。恢復正常時也會通知一次（ok_actions）。

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
  # 不加 KMS 加密：CloudWatch 告警無法使用 AWS 管理的 aws/sns 金鑰，
  # 自己建 KMS 金鑰每月 1 美元；告警內容只有指標名稱和數值，沒有使用者資料。
}

locals {
  alarm_actions = [aws_sns_topic.alerts.arn]
  metrics_ns    = "WeatherCast" # 從 log 轉出來的自訂指標

  # 程式印出的 JSON log 轉成指標（log 格式見 backend/src/logger.py）。
  # 這些指標只有在符合條件的 log 出現時才會有資料，不會產生額外的 API 呼叫。
  log_metrics = {
    # 外部 API 逾時或錯誤；回傳過期快取時也算，代表上游正在出問題
    UpstreamFailures = "{ $.message = \"upstream_timeout\" || $.message = \"upstream_error\" || $.message = \"serving_stale_cache\" }"
    # DynamoDB 讀寫失敗（斷路器打開期間跳過的呼叫不算）
    DynamoDBErrors = "{ $.message = \"dynamodb_error\" }"
    # 快取命中率 = CacheHits / (CacheHits + CacheMisses)，在 CloudWatch 用 metric math 算
    CacheHits   = "{ ($.message = \"weather_ok\" || $.message = \"fireworks_ok\") && $.source = \"cache\" }"
    CacheMisses = "{ ($.message = \"weather_ok\" || $.message = \"fireworks_ok\") && $.source = \"upstream\" }"
  }
}

resource "aws_cloudwatch_log_metric_filter" "app" {
  for_each = local.log_metrics

  name           = "${var.project_name}-${each.key}"
  log_group_name = aws_cloudwatch_log_group.lambda.name
  pattern        = each.value

  metric_transformation {
    name      = each.key
    namespace = local.metrics_ns
    value     = "1"
    unit      = "Count"
  }
}

locals {
  # 每個告警看 5 分鐘的總和（Duration 看最大值），一個週期超過門檻就通知
  alarms = {
    lambda-errors = {
      description = "Lambda 執行失敗（程式例外、逾時、記憶體不足）"
      namespace   = "AWS/Lambda"
      metric      = "Errors"
      dimensions  = { FunctionName = aws_lambda_function.api.function_name }
      statistic   = "Sum"
      threshold   = 1
    }
    lambda-throttles = {
      description = "Lambda 因為同時執行數不夠被拒絕"
      namespace   = "AWS/Lambda"
      metric      = "Throttles"
      dimensions  = { FunctionName = aws_lambda_function.api.function_name }
      statistic   = "Sum"
      threshold   = 1
    }
    lambda-duration = {
      description = "Lambda 執行時間接近逾時（${var.lambda_timeout_seconds} 秒的 80%）"
      namespace   = "AWS/Lambda"
      metric      = "Duration"
      dimensions  = { FunctionName = aws_lambda_function.api.function_name }
      statistic   = "Maximum"
      threshold   = var.lambda_timeout_seconds * 1000 * 0.8
    }
    api-5xx = {
      description = "API 回傳 5xx（上游失敗的 502/504 和 Lambda 錯誤的 500）"
      namespace   = "AWS/ApiGateway"
      metric      = "5xx"
      dimensions  = { ApiId = aws_apigatewayv2_api.http.id }
      statistic   = "Sum"
      threshold   = var.alarm_5xx_per_5min
    }
    api-traffic-spike = {
      description = "5 分鐘內的請求數異常偏高，可能是被大量呼叫"
      namespace   = "AWS/ApiGateway"
      metric      = "Count"
      dimensions  = { ApiId = aws_apigatewayv2_api.http.id }
      statistic   = "Sum"
      threshold   = var.alarm_requests_per_5min
    }
    upstream-failures = {
      description = "Open-Meteo 或觀光署的 API 逾時或錯誤"
      namespace   = local.metrics_ns
      metric      = "UpstreamFailures"
      dimensions  = {}
      statistic   = "Sum"
      threshold   = 3
    }
    dynamodb-errors = {
      description = "DynamoDB 快取讀寫失敗（服務仍可用，但上游呼叫會變多）"
      namespace   = local.metrics_ns
      metric      = "DynamoDBErrors"
      dimensions  = {}
      statistic   = "Sum"
      threshold   = 1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "alarms" {
  for_each = local.alarms

  alarm_name          = "${var.project_name}-${each.key}"
  alarm_description   = each.value.description
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dimensions
  statistic           = each.value.statistic
  period              = 300
  evaluation_periods  = 1
  threshold           = each.value.threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  # 自訂指標要等 log 轉出第一筆資料後才存在，建立告警時不需要它已經存在
  depends_on = [aws_cloudwatch_log_metric_filter.app]
}
