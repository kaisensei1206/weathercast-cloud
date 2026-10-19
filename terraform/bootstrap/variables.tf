variable "project_name" {
  description = "資源名稱的前綴"
  type        = string
  default     = "weathercast"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.project_name))
    error_message = "project_name 只能用小寫英文、數字和連字號，長度 3 到 21 個字元。"
  }
}

variable "region" {
  description = "AWS Region"
  type        = string
  default     = "ap-northeast-1"
}

variable "noncurrent_version_retention_days" {
  description = "state 舊版本保留天數；保留舊版本才能在 state 損毀時還原"
  type        = number
  default     = 90

  validation {
    condition     = var.noncurrent_version_retention_days >= 1
    error_message = "至少保留 1 天。"
  }
}

variable "github_repository" {
  description = "可以使用部署角色的 GitHub repo（owner/name）"
  type        = string
  default     = "kaisensei1206/weathercast-cloud"

  validation {
    condition     = can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "github_repository 的格式是 owner/name。"
  }
}

# GitHub 的 OIDC token 在 sub 裡同時寫入名稱和不會變的數字 ID（immutable subject），
# 例如 repo:owner@123/name@456:ref:refs/heads/main。帳號或 repo 改名、或有人刪掉後用同名重建，ID 都不會相同。
# 查詢：gh api repos/<owner>/<name> --jq '.owner.id, .id'
variable "github_owner_id" {
  description = "github_repository 擁有者（帳號或組織）的數字 ID"
  type        = number
  default     = 134856648
}

variable "github_repository_id" {
  description = "github_repository 的數字 ID"
  type        = number
  default     = 1421996870
}
