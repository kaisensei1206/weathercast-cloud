terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # state 放在 bootstrap 建立的 S3 bucket。bucket 名稱含帳號 ID，不寫死在這裡，
  # 而是在 init 時用 -backend-config="bucket=..." 帶入（見 bootstrap 的 output）。
  backend "s3" {
    key          = "weathercast/main.tfstate"
    region       = "ap-northeast-1"
    encrypt      = true
    use_lockfile = true # S3 原生鎖（Terraform 1.10+），避免兩個人同時 apply，不需要 DynamoDB lock table
  }
}

# 憑證不寫在這裡：AWS provider 會從環境變數、~/.aws 設定檔或 CI 的 OIDC 取得
provider "aws" {
  region = var.region

  # 每個資源都自動加上這些 tag，方便在帳單和主控台篩選本專案的資源
  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
      Stack     = "main"
    }
  }
}
