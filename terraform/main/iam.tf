# Lambda 執行角色：只允許 Lambda 服務使用，權限只有「讀寫這張快取表」和「寫自己的 log」

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid = "CacheReadWrite"
    # 程式只用到 GetItem 和 PutItem，沒有 Scan、Query、DeleteItem
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.cache.arn]
  }

  statement {
    sid = "WriteOwnLogs"
    # log group 由 Terraform 建立，所以不給 logs:CreateLogGroup
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

# 用 inline policy 而不是 AWS 受管的 AWSLambdaBasicExecutionRole：
# 受管 policy 允許寫入帳號內「所有」log group，這裡只開放自己的
resource "aws_iam_role_policy" "lambda" {
  name   = "${var.project_name}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}
