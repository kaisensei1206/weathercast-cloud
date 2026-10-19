# GitHub Actions 用 OIDC 換取 AWS 臨時憑證，不需要在 GitHub 存放長期金鑰。
#
# 部署角色只做一件事：把新版程式碼更新到「已經存在」的 Lambda。
# 它可以讀取主 stack 的資源（terraform plan 需要），但不能建立、刪除任何資源，也不能改 IAM。
# 新增或修改基礎設施（例如加資料表、改權限）仍由人在本機執行 terraform apply。

# GitHub 的 OIDC 身分提供者，整個帳號只需要一個
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "github_deploy_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    # token 必須是發給 AWS STS 的
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # 只有這個 repo 的 main 分支上執行的 workflow 能使用這個角色；
    # PR、其他分支、fork 拿到的 token 的 sub 都不一樣，會被拒絕
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "${var.project_name}-github-deploy"
  description          = "GitHub Actions deploys Lambda code from ${var.github_repository} main"
  assume_role_policy   = data.aws_iam_policy_document.github_deploy_assume.json
  max_session_duration = 3600
}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  arn_prefix   = "${var.region}:${local.account_id}"
  function_arn = "arn:aws:lambda:${local.arn_prefix}:function:${var.project_name}-api"
  log_groups   = ["/aws/lambda/${var.project_name}-api", "/aws/apigateway/${var.project_name}-api"]
}

data "aws_iam_policy_document" "github_deploy" {
  # --- Terraform state：只能讀寫主 stack 的 state 和鎖檔 ---
  statement {
    sid       = "ListStateBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.tf_state.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["weathercast/main.tfstate*"]
    }
  }

  statement {
    sid       = "ReadWriteMainState"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.tf_state.arn}/weathercast/main.tfstate*"] # 含 .tflock 鎖檔
  }

  # --- terraform plan 會重新讀取每個資源的現況，所以需要讀取權限 ---
  statement {
    sid       = "ReadLambda"
    actions   = ["lambda:Get*", "lambda:List*"]
    resources = [local.function_arn]
  }

  statement {
    sid       = "ReadCacheTable"
    actions   = ["dynamodb:Describe*", "dynamodb:ListTagsOfResource"]
    resources = ["arn:aws:dynamodb:${local.arn_prefix}:table/${var.project_name}-cache"]
  }

  statement {
    sid       = "ReadLambdaRole"
    actions   = ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies"]
    resources = ["arn:aws:iam::${local.account_id}:role/${var.project_name}-lambda"]
  }

  statement {
    sid     = "ReadLogGroupTags"
    actions = ["logs:ListTagsForResource", "logs:ListTagsLogGroup"]
    resources = flatten([
      for name in local.log_groups : [
        "arn:aws:logs:${local.arn_prefix}:log-group:${name}",
        "arn:aws:logs:${local.arn_prefix}:log-group:${name}:*",
      ]
    ])
  }

  statement {
    # DescribeLogGroups 是列表型 API，AWS 要求對整個 log-group 範圍授權；只能讀，不能改
    sid       = "ListLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${local.arn_prefix}:log-group:*"]
  }

  statement {
    # HTTP API 的 ID 在主 stack 建立時才產生，這裡無法事先指定，所以開放這個 Region 的 API 唯讀
    sid       = "ReadHttpApi"
    actions   = ["apigateway:GET"]
    resources = ["arn:aws:apigateway:${var.region}::/apis/*", "arn:aws:apigateway:${var.region}::/tags/*"]
  }

  # --- 唯一的寫入權限：更新這一個 Lambda 的程式碼和設定 ---
  # 沒有 iam:PassRole，所以無法把 Lambda 換成別的角色
  statement {
    sid       = "UpdateLambda"
    actions   = ["lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration"]
    resources = [local.function_arn]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${var.project_name}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
