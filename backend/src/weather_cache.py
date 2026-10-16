"""DynamoDB 快取：每個城市一筆資料，保存最近一次從 Open-Meteo 取得的天氣。

這個模組只負責讀寫 DynamoDB 和轉換資料格式；
「什麼時候用快取、什麼時候呼叫 Open-Meteo」由 weather_service 決定。

每筆資料有兩個時間：
- fresh_until：超過就要重新向 Open-Meteo 取資料（預設 10 分鐘）
- expires_at：DynamoDB TTL 屬性，超過後 DynamoDB 會自動刪除（預設 24 小時）
兩者分開，Open-Meteo 失敗時才有「過期但還能用」的舊資料可以回傳。
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_FRESH_SECONDS = 600
DEFAULT_RETAIN_SECONDS = 86400

# boto3 預設逾時 60 秒，DynamoDB 一卡住就會拖住整個 Lambda。
# 快取失敗本來就會改查 Open-Meteo，所以不重試，寧可快點放棄。
# 最壞情況：讀 2 秒 + Open-Meteo 3 秒 + 寫 2 秒，仍在 Lambda 的 10 秒逾時內。
BOTO_CONFIG = Config(
    connect_timeout=1,
    read_timeout=1,
    retries={"total_max_attempts": 1, "mode": "standard"},
)


class CacheError(Exception):
    """DynamoDB 讀寫失敗，或快取裡的資料無法使用。"""


@dataclass(frozen=True)
class CacheEntry:
    current: dict
    fetched_at: int
    fresh_until: int
    expires_at: int

    def is_fresh(self, now: int) -> bool:
        return now < self.fresh_until

    def is_expired(self, now: int) -> bool:
        # TTL 刪除會延遲，讀到已過 expires_at 但還沒被刪掉的資料，要當作不存在
        return now >= self.expires_at


class WeatherCache:
    def __init__(
        self,
        table,
        fresh_seconds: int = DEFAULT_FRESH_SECONDS,
        retain_seconds: int = DEFAULT_RETAIN_SECONDS,
    ):
        if fresh_seconds <= 0 or retain_seconds < fresh_seconds:
            raise ValueError("需要 0 < fresh_seconds <= retain_seconds")
        self.table = table
        self.fresh_seconds = fresh_seconds
        self.retain_seconds = retain_seconds

    def get(self, city_id: str) -> CacheEntry | None:
        try:
            item = self.table.get_item(Key={"city_id": city_id}).get("Item")
        except (BotoCoreError, ClientError) as exc:
            raise CacheError(f"get_item failed: {exc}") from exc
        if item is None:
            return None

        try:
            current = json.loads(item["payload"])
            if not isinstance(current, dict):
                raise TypeError("payload is not a JSON object")
            return CacheEntry(
                current=current,
                fetched_at=int(item["fetched_at"]),
                fresh_until=int(item["fresh_until"]),
                expires_at=int(item["expires_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheError(f"invalid cache item: {exc!r}") from exc

    def put(self, city_id: str, current: dict, fetched_at: int) -> None:
        item = {
            "city_id": city_id,
            # 存成 JSON 字串：boto3 不接受 float，要轉成 Decimal，讀出來還要轉回來
            "payload": json.dumps(current, ensure_ascii=False),
            "fetched_at": fetched_at,
            "fresh_until": fetched_at + self.fresh_seconds,
            "expires_at": fetched_at + self.retain_seconds,
        }
        try:
            self.table.put_item(Item=item)
        except (BotoCoreError, ClientError) as exc:
            raise CacheError(f"put_item failed: {exc}") from exc


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise ValueError(f"{name} 必須是正整數，目前是 {raw!r}")
    return value


def cache_from_env(env: Mapping[str, str]) -> WeatherCache | None:
    """依環境變數建立快取；沒設定 CACHE_TABLE 就回傳 None（停用快取）。

    設定值錯誤時直接丟出 ValueError：在 Lambda 冷啟動就失敗，比默默用錯的值繼續跑容易發現。
    """
    table_name = env.get("CACHE_TABLE", "").strip()
    if not table_name:
        return None
    fresh = _positive_int(env, "CACHE_FRESH_SECONDS", DEFAULT_FRESH_SECONDS)
    retain = _positive_int(env, "CACHE_RETAIN_SECONDS", DEFAULT_RETAIN_SECONDS)
    table = boto3.resource("dynamodb", config=BOTO_CONFIG).Table(table_name)
    return WeatherCache(table, fresh, retain)
