output "api_base_url" {
  description = "API 網址（不含路徑）"
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "health_url" {
  description = "部署後可以直接用瀏覽器或 curl 打開的健康檢查網址"
  value       = "${aws_apigatewayv2_api.http.api_endpoint}/api/health"
}

output "weather_example_url" {
  value = "${aws_apigatewayv2_api.http.api_endpoint}/api/weather?city=Tainan"
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}

output "lambda_log_group" {
  description = "Lambda 的 log（程式印出的 JSON log 在這裡）"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "api_access_log_group" {
  description = "API Gateway 的存取紀錄"
  value       = aws_cloudwatch_log_group.api_access.name
}

output "cache_table_name" {
  value = aws_dynamodb_table.cache.name
}

output "frontend_url" {
  description = "前端網址（CloudFront）；/api/* 也可以從這個網址呼叫"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "frontend_bucket" {
  description = "CD 上傳前端檔案的 S3 bucket"
  value       = aws_s3_bucket.frontend.bucket
}

output "cloudfront_distribution_id" {
  description = "CD 部署後清除 CloudFront 快取用"
  value       = aws_cloudfront_distribution.frontend.id
}
