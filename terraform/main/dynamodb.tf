# 天氣快取：每個城市一筆，Partition Key 是正規化後的城市 ID（例如 tainan）
resource "aws_dynamodb_table" "cache" {
  name         = "${var.project_name}-cache"
  billing_mode = "PAY_PER_REQUEST" # On-Demand：用多少付多少，沒有請求就不收容量費
  hash_key     = "city_id"

  # 只需要宣告 key 的屬性；payload、fetched_at 等其他欄位不用事先定義
  attribute {
    name = "city_id"
    type = "S"
  }

  # DynamoDB 會在 expires_at（Unix 秒）之後自動刪除資料。
  # 刪除時間不準，所以程式還是會自己檢查有沒有過期。
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # 快取資料隨時可以重新從 Open-Meteo 取得，不開 Point-in-time recovery，省下備份費用
}
