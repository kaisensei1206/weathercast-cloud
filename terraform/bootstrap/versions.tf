# 一次性的基礎設施：存放主 stack Terraform state 的 S3 bucket。
# 這個資料夾自己用 local state，由人手動 apply 一次；之後主 stack（../main）的 state 都放進這個 bucket。
# 第八階段（GitHub Actions）會在這裡加上 GitHub OIDC 與部署用的 IAM Role。

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}
