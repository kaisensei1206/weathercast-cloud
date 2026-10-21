# 前端：S3 私有 bucket 放打包好的檔案，CloudFront 提供 HTTPS 網址。
#
#   瀏覽器 ──HTTPS──► CloudFront ─┬─ /api/*  ──► API Gateway（同網域，不需要 CORS）
#                                  └─ 其他    ──► S3 私有 bucket（只有這個 CloudFront 能讀）
#
# 檔案由 CD 上傳（見 .github/workflows/ci-cd.yml），Terraform 只建立空的 bucket 和 distribution。

data "aws_caller_identity" "current" {}

locals {
  frontend_bucket = "${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}"
  s3_origin_id    = "s3-frontend"
  api_origin_id   = "api-gateway"

  # AWS 內建（managed）的 CloudFront policy，ID 是 AWS 公開的固定值，所有帳號都一樣。
  # 直接寫 ID，而不是用 data source 查名稱，部署角色就不需要額外的「列出 policy」權限。
  cache_policy_caching_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  cache_policy_caching_disabled  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  origin_request_all_except_host = "b689b0a8-53d0-40ab-baf2-68738e2966ac" # AllViewerExceptHostHeader
  response_headers_security      = "67f7725c-6f97-4210-82d7-5512b31e9d03" # SecurityHeadersPolicy
}

resource "aws_s3_bucket" "frontend" {
  bucket = local.frontend_bucket

  # 裡面只有 npm run build 的結果，隨時可以重新產生；
  # 允許 terraform destroy 時連同檔案一起刪除，不然 bucket 不是空的會刪不掉
  force_destroy = true
}

# 四項全開：任何人都不能把 bucket 或檔案設成公開
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-S3 加密。OAC 搭配 SSE-KMS 還要另外給 CloudFront KMS 權限，靜態網站用不到
resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# OAC：CloudFront 讀 S3 時用 SigV4 簽章，S3 才能確認請求真的來自這個 distribution
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-frontend"
  description                       = "CloudFront reads the private frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  comment             = "${var.project_name} frontend and API"
  default_root_object = "index.html"
  http_version        = "http2and3"
  is_ipv6_enabled     = true
  price_class         = "PriceClass_200" # 包含亞洲節點；PriceClass_All 多的南美、澳洲節點用不到

  origin {
    origin_id                = local.s3_origin_id
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    origin_id   = local.api_origin_id
    domain_name = replace(aws_apigatewayv2_api.http.api_endpoint, "https://", "")

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only" # HTTP API 只接受 HTTPS
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # 靜態檔：可以快取。index.html 由 CD 設成 no-cache，每次都會回 S3 確認有沒有新版
  default_cache_behavior {
    target_origin_id           = local.s3_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = local.cache_policy_caching_optimized
    response_headers_policy_id = local.response_headers_security
  }

  # API：不快取（DynamoDB 已經有 10 分鐘快取，CloudFront 再快取一層會讓資料新鮮度難以預測）。
  # 不轉送 Host header，否則 API Gateway 會用 CloudFront 的網域名稱找 API，找不到就回 403。
  ordered_cache_behavior {
    path_pattern               = "/api/*"
    target_origin_id           = local.api_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = local.cache_policy_caching_disabled
    origin_request_policy_id   = local.origin_request_all_except_host
    response_headers_policy_id = local.response_headers_security
  }

  # 刻意不設定 custom_error_response（把 403/404 改回 index.html）：
  # 這個前端只有一頁、沒有 router，而且這個設定對 /api/* 也有效，
  # 會把 API 的 404 city_not_found JSON 換成 HTML，前端就分不出「找不到城市」。

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # 用 CloudFront 預設的 *.cloudfront.net 憑證，不需要另外買網域
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# 只允許「這一個」distribution 透過 OAC 讀檔案。
# 沒有 AWS:SourceArn 條件的話，帳號裡任何 CloudFront distribution 都能讀這個 bucket。
data "aws_iam_policy_document" "frontend_bucket" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket.json

  # 先套用 Block Public Access，再放 policy；這個 policy 不算公開，所以不會被擋
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}
