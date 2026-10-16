output "state_bucket" {
  description = "主 stack 的 terraform init 要用的 bucket 名稱"
  value       = aws_s3_bucket.tf_state.bucket
}

output "main_stack_init_command" {
  description = "在 terraform/main 執行的初始化指令"
  value       = "terraform init -backend-config=\"bucket=${aws_s3_bucket.tf_state.bucket}\""
}
