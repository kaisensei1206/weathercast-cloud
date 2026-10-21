"""weather_cache：DynamoDB 讀寫、資料格式轉換、環境變數設定。

DynamoDB 用 moto 在記憶體裡模擬；逾時這類 moto 做不到的情況，用會丟例外的假資料表模擬。
"""

from decimal import Decimal

import boto3
import pytest
from botocore.exceptions import ReadTimeoutError

from fakes import TABLE_NAME
from weather_cache import (
    DEFAULT_FRESH_SECONDS,
    DEFAULT_RETAIN_SECONDS,
    CacheEntry,
    CacheError,
    WeatherCache,
    cache_from_env,
)

NOW = 1792148400
CURRENT = {"time": "2026-10-16T19:45", "temperature": 27.7, "description": "大致晴朗"}


class TimeoutTable:
    """模擬 DynamoDB 沒有回應：每個操作都丟出 botocore 的逾時例外。"""

    def get_item(self, **kwargs):
        raise ReadTimeoutError(endpoint_url="https://dynamodb.ap-northeast-1.amazonaws.com")

    put_item = get_item


# --- 讀寫 ---------------------------------------------------------------------


def test_put_writes_item_with_freshness_and_ttl(cache_table):
    WeatherCache(cache_table).put("tainan", CURRENT, NOW)

    item = cache_table.get_item(Key={"city_id": "tainan"})["Item"]
    assert item == {
        "city_id": "tainan",
        "payload": '{"time": "2026-10-16T19:45", "temperature": 27.7, "description": "大致晴朗"}',
        "fetched_at": Decimal(NOW),
        "fresh_until": Decimal(NOW + DEFAULT_FRESH_SECONDS),
        "expires_at": Decimal(NOW + DEFAULT_RETAIN_SECONDS),
    }


def test_get_returns_what_put_stored(cache_table):
    cache = WeatherCache(cache_table, fresh_seconds=60, retain_seconds=3600)
    cache.put("tainan", CURRENT, NOW)

    assert cache.get("tainan") == CacheEntry(
        current=CURRENT, fetched_at=NOW, fresh_until=NOW + 60, expires_at=NOW + 3600
    )


def test_get_returns_none_when_city_not_cached(cache_table):
    assert WeatherCache(cache_table).get("tainan") is None


def test_put_overwrites_previous_item(cache_table):
    cache = WeatherCache(cache_table)
    cache.put("tainan", CURRENT, NOW)
    cache.put("tainan", {**CURRENT, "temperature": 30.1}, NOW + 700)

    entry = cache.get("tainan")
    assert entry.current["temperature"] == 30.1
    assert entry.fetched_at == NOW + 700


# --- 新鮮度與保留期限 ---------------------------------------------------------


def test_entry_freshness_boundaries():
    entry = CacheEntry(current={}, fetched_at=NOW, fresh_until=NOW + 600, expires_at=NOW + 86400)

    assert entry.is_fresh(NOW + 599)
    assert not entry.is_fresh(NOW + 600)
    assert not entry.is_expired(NOW + 86399)
    assert entry.is_expired(NOW + 86400)


# --- 失敗情況 -----------------------------------------------------------------


def test_missing_table_raises_cache_error(cache_table):
    # 資料表不存在、沒有權限這類錯誤，boto3 會丟出 ClientError
    table = boto3.resource("dynamodb").Table("table-that-does-not-exist")
    with pytest.raises(CacheError, match="get_item failed"):
        WeatherCache(table).get("tainan")
    with pytest.raises(CacheError, match="put_item failed"):
        WeatherCache(table).put("tainan", CURRENT, NOW)


def test_timeout_raises_cache_error():
    cache = WeatherCache(TimeoutTable())
    with pytest.raises(CacheError):
        cache.get("tainan")
    with pytest.raises(CacheError):
        cache.put("tainan", CURRENT, NOW)


@pytest.mark.parametrize(
    "item",
    [
        pytest.param({"payload": "not json"}, id="payload-not-json"),
        pytest.param({"payload": "[1, 2]"}, id="payload-not-object"),
        pytest.param({"fresh_until": "soon"}, id="number-is-text"),
        pytest.param({"expires_at": None}, id="field-removed"),
    ],
)
def test_corrupted_item_raises_cache_error(cache_table, item):
    WeatherCache(cache_table).put("tainan", CURRENT, NOW)
    stored = cache_table.get_item(Key={"city_id": "tainan"})["Item"]
    stored.update(item)
    stored = {k: v for k, v in stored.items() if v is not None}
    cache_table.put_item(Item=stored)

    with pytest.raises(CacheError, match="invalid cache item"):
        WeatherCache(cache_table).get("tainan")


@pytest.mark.parametrize(("fresh", "retain"), [(0, 600), (-1, 600), (600, 599)])
def test_rejects_invalid_durations(fresh, retain):
    with pytest.raises(ValueError):
        WeatherCache(table=None, fresh_seconds=fresh, retain_seconds=retain)


# --- 環境變數 -----------------------------------------------------------------


@pytest.mark.parametrize("env", [{}, {"CACHE_TABLE": ""}, {"CACHE_TABLE": "   "}])
def test_cache_disabled_without_table_name(env):
    assert cache_from_env(env) is None


def test_cache_from_env_uses_defaults(cache_table):
    cache = cache_from_env({"CACHE_TABLE": TABLE_NAME})

    assert cache.table.name == TABLE_NAME
    assert cache.fresh_seconds == DEFAULT_FRESH_SECONDS
    assert cache.retain_seconds == DEFAULT_RETAIN_SECONDS


def test_cache_from_env_reads_durations(cache_table):
    cache = cache_from_env(
        {"CACHE_TABLE": TABLE_NAME, "CACHE_FRESH_SECONDS": "300", "CACHE_RETAIN_SECONDS": "7200"}
    )
    assert (cache.fresh_seconds, cache.retain_seconds) == (300, 7200)


def test_cache_from_env_sets_short_dynamodb_timeouts(cache_table):
    config = cache_from_env({"CACHE_TABLE": TABLE_NAME}).table.meta.client.meta.config

    assert config.connect_timeout == 1
    assert config.read_timeout == 1
    assert config.retries == {"total_max_attempts": 1, "mode": "standard"}


@pytest.mark.parametrize(
    "env",
    [
        {"CACHE_FRESH_SECONDS": "ten minutes"},
        {"CACHE_FRESH_SECONDS": "0"},
        {"CACHE_RETAIN_SECONDS": "-1"},
        {"CACHE_FRESH_SECONDS": "600", "CACHE_RETAIN_SECONDS": "60"},
    ],
)
def test_cache_from_env_rejects_bad_values(env):
    with pytest.raises(ValueError):
        cache_from_env({"CACHE_TABLE": TABLE_NAME, **env})


# --- DynamoDB 故障時的保護 ----------------------------------------------------


class FlakyTable:
    """可以隨時切換成故障的資料表，並記錄被呼叫幾次。"""

    def __init__(self, table):
        self.table = table
        self.broken = False
        self.calls = 0

    def get_item(self, **kwargs):
        return self._call("get_item", kwargs)

    def put_item(self, **kwargs):
        return self._call("put_item", kwargs)

    def _call(self, name, kwargs):
        self.calls += 1
        if self.broken:
            raise ReadTimeoutError(endpoint_url="https://dynamodb.ap-northeast-1.amazonaws.com")
        return getattr(self.table, name)(**kwargs)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_get_falls_back_to_memory_when_dynamodb_fails(cache_table):
    table = FlakyTable(cache_table)
    cache = WeatherCache(table, monotonic=Clock())
    cache.put("tainan", CURRENT, NOW)
    table.broken = True

    assert cache.get("tainan").current == CURRENT
    with pytest.raises(CacheError):
        cache.get("taipei")  # 記憶體裡也沒有，才丟出 CacheError


def test_put_keeps_the_entry_in_memory_when_dynamodb_fails(cache_table):
    table = FlakyTable(cache_table)
    clock = Clock()
    cache = WeatherCache(table, monotonic=clock)
    table.broken = True
    with pytest.raises(CacheError):
        cache.put("tainan", CURRENT, NOW)

    # DynamoDB 恢復了，但那筆資料當時沒寫進去：從記憶體補上
    table.broken = False
    clock.now += 60
    assert cache.get("tainan").fetched_at == NOW


def test_breaker_skips_dynamodb_for_a_while_after_a_failure(cache_table, capsys):
    table = FlakyTable(cache_table)
    clock = Clock()
    cache = WeatherCache(table, breaker_seconds=30, monotonic=clock)
    table.broken = True

    with pytest.raises(CacheError, match="get_item failed"):
        cache.get("tainan")
    clock.now += 29
    with pytest.raises(CacheError, match="skipped"):
        cache.get("tainan")
    assert table.calls == 1  # 第二次沒有真的呼叫 DynamoDB

    table.broken = False
    clock.now += 1
    assert cache.get("tainan") is None
    assert table.calls == 2
    assert capsys.readouterr().out.count('"dynamodb_error"') == 1


def test_corrupted_item_does_not_open_the_breaker(cache_table):
    table = FlakyTable(cache_table)
    cache = WeatherCache(table, monotonic=Clock())
    cache_table.put_item(Item={"city_id": "tainan", "payload": "not json"})

    for _ in range(2):
        with pytest.raises(CacheError, match="invalid cache item"):
            cache.get("tainan")
    assert table.calls == 2
