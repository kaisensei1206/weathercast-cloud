data "aws_caller_identity" "current" {}

# bucket 名稱全球唯一，加上帳號 ID 避免和別人撞名
resource "aws_s3_bucket" "tf_state" {
  bucket = "${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}"

  # state 不見會讓 Terraform 失去對所有資源的追蹤，禁止用 terraform destroy 刪掉
  lifecycle {
    prevent_destroy = true
  }
}

# 開啟版本控制：state 被寫壞或誤刪時，可以還原到前一版
resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 舊版本留一段時間後自動刪除，避免 bucket 無限長大
resource "aws_s3_bucket_lifecycle_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }

  depends_on = [aws_s3_bucket_versioning.tf_state]
}

# 拒絕所有非 HTTPS 的存取
data "aws_iam_policy_document" "tf_state" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.tf_state.arn, "${aws_s3_bucket.tf_state.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  policy = data.aws_iam_policy_document.tf_state.json

  # bucket policy 要在公開存取封鎖之後才設定，避免兩者同時修改時發生衝突
  depends_on = [aws_s3_bucket_public_access_block.tf_state]
}
