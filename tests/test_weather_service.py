"""weather_service：輸入驗證、回應格式、快取流程。

get_weather 的 fetcher、clock、cache 可以替換（依賴注入），
所以這裡不碰網路、不 mock urllib；DynamoDB 用 moto 在記憶體裡模擬。
"""

import json

import boto3
import pytest
from moto import mock_aws

from fakes import SAMPLE_CURRENT
from weather_cache import CacheError, WeatherCache
from weather_client import UpstreamError, UpstreamTimeout
from weather_service import (
    MAX_CITY_LENGTH,
    CityNotFound,
    InvalidCity,
    MissingCity,
    get_weather,
    resolve_city,
)

FIXED_TIME = 1792148400.9


def fake_fetcher(city):
    return dict(SAMPLE_CURRENT)


def must_not_fetch(city):
    pytest.fail("輸入無效時不應該呼叫 Open-Meteo")


def test_get_weather_maps_open_meteo_fields_to_api_format():
    result = get_weather("台南", fetcher=fake_fetcher, clock=lambda: FIXED_TIME)

    assert result == {
        "city": {"id": "tainan", "name": "臺南市", "name_en": "Tainan"},
        "current": {
            "time": "2026-10-16T19:45",
            "temperature": 27.7,
            "apparent_temperature": 31.9,
            "humidity": 76,
            "precipitation": 0.0,
            "wind_speed": 8.7,
            "weather_code": 1,
            "description": "大致晴朗",
        },
        "meta": {
            "source": "upstream",
            "stale": False,
            "fetched_at": 1792148400,
            "provider": "open-meteo",
        },
    }


def test_get_weather_passes_resolved_city_to_fetcher():
    received = []

    def fetcher(city):
        received.append(city)
        return dict(SAMPLE_CURRENT)

    get_weather("  KAOHSIUNG ", fetcher=fetcher)
    assert [c.id for c in received] == ["kaohsiung"]


def test_unknown_weather_code_is_described_as_unknown():
    def fetcher(city):
        return {**SAMPLE_CURRENT, "weather_code": 42}

    assert get_weather("Tainan", fetcher=fetcher)["current"]["description"] == "未知"


@pytest.mark.parametrize("query", [None, "", "   ", "\t\n"])
def test_missing_city(query):
    with pytest.raises(MissingCity):
        get_weather(query, fetcher=must_not_fetch)


def test_city_longer_than_limit_is_invalid():
    with pytest.raises(InvalidCity):
        get_weather("a" * (MAX_CITY_LENGTH + 1), fetcher=must_not_fetch)


def test_city_at_length_limit_is_looked_up():
    # 剛好 50 字元還是合法輸入，只是查不到
    with pytest.raises(CityNotFound):
        resolve_city("a" * MAX_CITY_LENGTH)


def test_unknown_city_keeps_trimmed_query_for_error_message():
    with pytest.raises(CityNotFound) as info:
        get_weather("  Tokyo  ", fetcher=must_not_fetch)
    assert info.value.query == "Tokyo"


@pytest.mark.parametrize("exc", [UpstreamTimeout("read timeout"), UpstreamError("HTTP 503")])
def test_upstream_errors_propagate_to_handler(exc):
    def fetcher(city):
        raise exc

    with pytest.raises(type(exc)):
        get_weather("Tainan", fetcher=fetcher)


# --- 快取流程 -----------------------------------------------------------------
# 用 moto 模擬的 DynamoDB，加上固定的 clock，精確控制「現在」是快取寫入後的第幾秒。

NOW = 1792148400


class Upstream:
    """假的 fetcher：記錄被呼叫的次數，可以設定成丟出例外。"""

    def __init__(self, exc=None, current=None):
        self.calls = 0
        self.exc = exc
        self.current = current or SAMPLE_CURRENT

    def __call__(self, city):
        self.calls += 1
        if self.exc:
            raise self.exc
        return dict(self.current)


class BrokenCache:
    """模擬 DynamoDB 故障：讀寫都丟出 CacheError。"""

    def get(self, city_id):
        raise CacheError("get_item failed: timeout")

    def put(self, city_id, current, fetched_at):
        raise CacheError("put_item failed: timeout")


class UntouchableCache:
    def get(self, city_id):
        pytest.fail("輸入無效時不應該讀快取")

    put = get


@pytest.fixture
def cache(cache_table):
    return WeatherCache(cache_table, fresh_seconds=600, retain_seconds=86400)


def query(cache, upstream, at, city="Tainan"):
    return get_weather(city, fetcher=upstream, clock=lambda: at, cache=cache)


def log_messages(capsys):
    return [json.loads(line)["message"] for line in capsys.readouterr().out.splitlines()]


def test_cache_miss_calls_upstream_and_stores_result(cache):
    upstream = Upstream()
    result = query(cache, upstream, NOW)

    assert upstream.calls == 1
    assert result["meta"] == {
        "source": "upstream",
        "stale": False,
        "fetched_at": NOW,
        "provider": "open-meteo",
    }
    entry = cache.get("tainan")
    assert entry.current == result["current"]
    assert (entry.fetched_at, entry.fresh_until, entry.expires_at) == (NOW, NOW + 600, NOW + 86400)


def test_cache_hit_skips_upstream(cache):
    first = query(cache, Upstream(), NOW)
    second = query(cache, must_not_fetch, NOW + 599)

    assert second["meta"]["source"] == "cache"
    assert second["meta"]["stale"] is False
    # fetched_at 是資料從 Open-Meteo 取得的時間，不是這次請求的時間
    assert second["meta"]["fetched_at"] == NOW
    assert second["current"] == first["current"]


def test_different_spellings_share_one_cache_item(cache):
    query(cache, Upstream(), NOW, city="台南")
    assert query(cache, must_not_fetch, NOW + 1, city=" tainan ")["meta"]["source"] == "cache"


def test_expired_entry_is_refreshed_from_upstream(cache):
    query(cache, Upstream(), NOW)
    upstream = Upstream(current={**SAMPLE_CURRENT, "temperature_2m": 30.1})

    # 剛好第 600 秒就算過期
    result = query(cache, upstream, NOW + 600)

    assert upstream.calls == 1
    assert result["meta"]["source"] == "upstream"
    assert result["current"]["temperature"] == 30.1
    assert cache.get("tainan").fetched_at == NOW + 600


@pytest.mark.parametrize("exc", [UpstreamTimeout("read timeout"), UpstreamError("HTTP 503")])
def test_upstream_failure_serves_stale_cache(cache, capsys, exc):
    first = query(cache, Upstream(), NOW)
    capsys.readouterr()

    result = query(cache, Upstream(exc=exc), NOW + 3600)

    assert result["current"] == first["current"]
    assert result["meta"]["source"] == "cache"
    assert result["meta"]["stale"] is True
    assert result["meta"]["fetched_at"] == NOW
    assert log_messages(capsys) == ["serving_stale_cache"]


def test_entry_past_retention_is_not_served_even_if_ttl_has_not_deleted_it(cache):
    query(cache, Upstream(), NOW)

    # DynamoDB TTL 刪除會延遲，資料可能還在；程式要自己判斷不能再用
    with pytest.raises(UpstreamTimeout):
        query(cache, Upstream(exc=UpstreamTimeout("read timeout")), NOW + 86400)


def test_upstream_failure_without_cache_still_raises(cache):
    with pytest.raises(UpstreamError):
        query(cache, Upstream(exc=UpstreamError("HTTP 503")), NOW)


def test_broken_cache_falls_back_to_upstream(capsys):
    upstream = Upstream()
    result = query(BrokenCache(), upstream, NOW)

    assert upstream.calls == 1
    assert result["meta"]["source"] == "upstream"
    assert log_messages(capsys) == ["cache_read_failed", "cache_write_failed"]


def test_missing_table_falls_back_to_upstream(capsys):
    # 資料表不存在或沒有權限：使用者照樣拿到資料，錯誤只出現在 log
    cache = WeatherCache(boto3.resource("dynamodb").Table("table-that-does-not-exist"))
    with mock_aws():
        result = query(cache, Upstream(), NOW)

    assert result["meta"]["source"] == "upstream"
    assert log_messages(capsys) == ["cache_read_failed", "cache_write_failed"]


@pytest.mark.parametrize("bad_query", [None, "   ", "x" * 51, "Tokyo"])
def test_invalid_input_never_touches_cache(bad_query):
    with pytest.raises((MissingCity, InvalidCity, CityNotFound)):
        get_weather(bad_query, fetcher=must_not_fetch, cache=UntouchableCache())
