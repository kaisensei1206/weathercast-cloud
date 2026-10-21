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
  description = "AWS Region；改這裡時，versions.tf 裡 backend 的 region 也要在 init 時用 -backend-config 改掉"
  type        = string
  default     = "ap-northeast-1"
}

variable "lambda_memory_mb" {
  description = "Lambda 記憶體（MB），CPU 會依比例分配"
  type        = number
  default     = 256

  validation {
    condition     = var.lambda_memory_mb >= 128 && var.lambda_memory_mb <= 1024
    error_message = "lambda_memory_mb 需介於 128 到 1024。"
  }
}

variable "lambda_timeout_seconds" {
  description = "Lambda 逾時秒數；要大於 Open-Meteo 的 3 秒加上 DynamoDB 讀寫的時間"
  type        = number
  default     = 10

  validation {
    # HTTP API 整合逾時上限是 30 秒，Lambda 超過也沒有意義
    condition     = var.lambda_timeout_seconds >= 5 && var.lambda_timeout_seconds <= 29
    error_message = "lambda_timeout_seconds 需介於 5 到 29。"
  }
}

variable "log_retention_days" {
  description = "CloudWatch Logs 保留天數；放太久會一直累積儲存費用"
  type        = number
  default     = 14

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 180, 365], var.log_retention_days)
    error_message = "log_retention_days 必須是 CloudWatch 支援的天數，例如 7、14、30。"
  }
}

variable "cache_fresh_seconds" {
  description = "快取新鮮期（秒），超過就重新呼叫 Open-Meteo"
  type        = number
  default     = 600

  validation {
    condition     = var.cache_fresh_seconds > 0
    error_message = "cache_fresh_seconds 必須大於 0。"
  }
}

variable "cache_retain_seconds" {
  description = "快取保留期（秒），也是 DynamoDB TTL 刪除的時間和舊資料最多能回傳多久"
  type        = number
  default     = 86400

  validation {
    condition     = var.cache_retain_seconds >= var.cache_fresh_seconds
    error_message = "cache_retain_seconds 不能小於 cache_fresh_seconds。"
  }
}

variable "api_throttle_rate_limit" {
  description = "API Gateway 每秒平均請求上限；超過回 429，不會呼叫 Lambda，是費用防線"
  type        = number
  default     = 10

  validation {
    condition     = var.api_throttle_rate_limit > 0
    error_message = "api_throttle_rate_limit 必須大於 0。"
  }
}

variable "api_throttle_burst_limit" {
  description = "API Gateway 瞬間可接受的請求數"
  type        = number
  default     = 20

  validation {
    condition     = var.api_throttle_burst_limit > 0
    error_message = "api_throttle_burst_limit 必須大於 0。"
  }
}

variable "cors_allow_origins" {
  description = <<-EOT
    允許跨網域呼叫 API 的網頁來源。正式環境的前端會透過 CloudFront 和 API 放在同一個網域，
    不需要 CORS；預設只開放本機的 Vite 開發伺服器，方便開發前端時直接呼叫線上 API。
  EOT
  type        = list(string)
  default     = ["http://localhost:5173"]

  validation {
    condition     = !contains(var.cors_allow_origins, "*")
    error_message = "不要使用 \"*\"，請列出明確的網址。"
  }
}

variable "fireworks_throttle_rate_limit" {
  description = "/api/fireworks 每秒平均請求上限；這條路由的回應最大，也是唯一會下載 zip 的上游，所以比其他路由低"
  type        = number
  default     = 2

  validation {
    condition     = var.fireworks_throttle_rate_limit > 0 && var.fireworks_throttle_rate_limit <= var.api_throttle_rate_limit
    error_message = "fireworks_throttle_rate_limit 必須大於 0，且不能超過 api_throttle_rate_limit。"
  }
}

variable "fireworks_throttle_burst_limit" {
  description = "/api/fireworks 瞬間可接受的請求數"
  type        = number
  default     = 5

  validation {
    condition     = var.fireworks_throttle_burst_limit > 0 && var.fireworks_throttle_burst_limit <= var.api_throttle_burst_limit
    error_message = "fireworks_throttle_burst_limit 必須大於 0，且不能超過 api_throttle_burst_limit。"
  }
}

variable "alarm_requests_per_5min" {
  description = "請求量突增告警：5 分鐘內的請求數達到多少就通知。節流上限 10 次/秒 = 5 分鐘最多 3000 次，預設是一半"
  type        = number
  default     = 1500

  validation {
    condition     = var.alarm_requests_per_5min > 0
    error_message = "alarm_requests_per_5min 必須大於 0。"
  }
}

variable "alarm_5xx_per_5min" {
  description = "5 分鐘內有幾個 5xx 就通知；偶爾一次上游逾時不用叫人"
  type        = number
  default     = 5

  validation {
    condition     = var.alarm_5xx_per_5min > 0
    error_message = "alarm_5xx_per_5min 必須大於 0。"
  }
}
