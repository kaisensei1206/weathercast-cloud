# 一次性的基礎設施，由人在本機 apply，state 存在本機（local state）：
# - 存放主 stack Terraform state 的 S3 bucket（main.tf）
# - GitHub Actions 用的 OIDC 身分提供者與部署角色（github_oidc.tf）

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
