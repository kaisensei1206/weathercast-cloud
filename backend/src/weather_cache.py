"""DynamoDB 快取：每個城市一筆資料，保存最近一次從 Open-Meteo 取得的天氣。

這個模組只負責讀寫 DynamoDB 和轉換資料格式；
「什麼時候用快取、什麼時候呼叫 Open-Meteo」由 weather_service 決定。

每筆資料有兩個時間：
- fresh_until：超過就要重新向 Open-Meteo 取資料（預設 10 分鐘）
- expires_at：DynamoDB TTL 屬性，超過後 DynamoDB 會自動刪除（預設 24 小時）
兩者分開，Open-Meteo 失敗時才有「過期但還能用」的舊資料可以回傳。

DynamoDB 故障時的保護（避免每個請求都打到上游）：
- 記憶體備援：每筆讀到或寫入的資料也留在這個 Lambda 實例的記憶體裡。
  DynamoDB 讀不到時改回傳記憶體裡的資料，所以每個實例每 10 分鐘對同一個 key
  最多呼叫上游一次，而不是每個請求都呼叫。
- 斷路器：DynamoDB 失敗一次後，接下來 30 秒不再嘗試，直接當作失敗，
  請求不會每次都卡在 1 秒的逾時上。
"""

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from logger import log

DEFAULT_FRESH_SECONDS = 600
DEFAULT_RETAIN_SECONDS = 86400
BREAKER_SECONDS = 30

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
        breaker_seconds: float = BREAKER_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        if fresh_seconds <= 0 or retain_seconds < fresh_seconds:
            raise ValueError("需要 0 < fresh_seconds <= retain_seconds")
        self.table = table
        self.fresh_seconds = fresh_seconds
        self.retain_seconds = retain_seconds
        self.breaker_seconds = breaker_seconds
        self.monotonic = monotonic  # 斷路器用的時鐘；和資料的時間（Unix 秒）無關
        self._memory: dict[str, CacheEntry] = {}
        self._skip_until = 0.0

    def _call(self, operation: str, call: Callable[[], Any]) -> Any:
        """呼叫 DynamoDB；失敗時記 log、打開斷路器，並轉成 CacheError。"""
        if self.monotonic() < self._skip_until:
            raise CacheError(f"{operation} skipped: DynamoDB failed recently")
        try:
            return call()
        except (BotoCoreError, ClientError) as exc:
            self._skip_until = self.monotonic() + self.breaker_seconds
            # CloudWatch 的 metric filter 計算這個訊息的次數，用來發告警
            log("error", "dynamodb_error", operation=operation, detail=str(exc))
            raise CacheError(f"{operation} failed: {exc}") from exc

    def get(self, city_id: str) -> CacheEntry | None:
        """讀快取。DynamoDB 失敗時改回傳記憶體裡的資料；記憶體也沒有才丟出 CacheError。"""
        try:
            item = self._call("get_item", lambda: self.table.get_item(Key={"city_id": city_id}))
        except CacheError:
            remembered = self._memory.get(city_id)
            if remembered is None:
                raise
            return remembered

        item = item.get("Item")
        if item is None:
            # 之前寫入 DynamoDB 失敗時，資料只在記憶體裡
            return self._memory.get(city_id)

        try:
            current = json.loads(item["payload"])
            if not isinstance(current, dict):
                raise TypeError("payload is not a JSON object")
            entry = CacheEntry(
                current=current,
                fetched_at=int(item["fetched_at"]),
                fresh_until=int(item["fresh_until"]),
                expires_at=int(item["expires_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheError(f"invalid cache item: {exc!r}") from exc
        self._memory[city_id] = entry
        return entry

    def put(self, city_id: str, current: dict, fetched_at: int) -> None:
        """寫快取。先寫記憶體，所以 DynamoDB 失敗時這筆資料仍然可以用。"""
        entry = CacheEntry(
            current=current,
            fetched_at=fetched_at,
            fresh_until=fetched_at + self.fresh_seconds,
            expires_at=fetched_at + self.retain_seconds,
        )
        self._memory[city_id] = entry
        item = {
            "city_id": city_id,
            # 存成 JSON 字串：boto3 不接受 float，要轉成 Decimal，讀出來還要轉回來
            "payload": json.dumps(current, ensure_ascii=False),
            "fetched_at": entry.fetched_at,
            "fresh_until": entry.fresh_until,
            "expires_at": entry.expires_at,
        }
        self._call("put_item", lambda: self.table.put_item(Item=item))


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
