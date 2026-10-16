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
