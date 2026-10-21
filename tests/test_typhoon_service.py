"""typhoon_service：快取流程和 weather_service 相同（新鮮就用、過期再查、失敗用舊資料）。

fetcher、clock、cache 都可以替換，所以這裡不碰網路；DynamoDB 用 moto 模擬。
"""

import pytest

from typhoon_service import CACHE_KEY, get_typhoons
from weather_cache import CacheError, WeatherCache
from weather_client import UpstreamError, UpstreamTimeout

NOW = 1792148400.5
TYPHOONS = [{"name": "鳳凰", "track": [], "forecast": []}]


def fetcher():
    return TYPHOONS


def failing(exc=None):
    def fetch():
        raise exc or UpstreamError("CWA HTTP 500")

    return fetch


def must_not_fetch():
    pytest.fail("快取還新鮮時不應該呼叫氣象署")


def test_without_cache_fetches_from_cwa():
    assert get_typhoons(fetcher, clock=lambda: NOW) == {
        "typhoons": TYPHOONS,
        "meta": {"source": "upstream", "stale": False, "fetched_at": 1792148400, "provider": "cwa"},
    }


def test_no_typhoon_is_a_normal_empty_answer():
    assert get_typhoons(lambda: [], clock=lambda: NOW)["typhoons"] == []


def test_upstream_error_without_cache_is_raised():
    with pytest.raises(UpstreamTimeout):
        get_typhoons(failing(UpstreamTimeout("slow")), clock=lambda: NOW)


def test_fresh_cache_is_used(cache_table):
    cache = WeatherCache(cache_table)
    get_typhoons(fetcher, clock=lambda: NOW, cache=cache)
    result = get_typhoons(must_not_fetch, clock=lambda: NOW + 60, cache=cache)
    assert result["typhoons"] == TYPHOONS
    assert result["meta"] == {
        "source": "cache",
        "stale": False,
        "fetched_at": 1792148400,
        "provider": "cwa",
    }


def test_shares_table_with_weather_under_its_own_key(cache_table):
    get_typhoons(fetcher, clock=lambda: NOW, cache=WeatherCache(cache_table))
    assert [i["city_id"] for i in cache_table.scan()["Items"]] == [CACHE_KEY]


def test_old_cache_is_refreshed(cache_table):
    cache = WeatherCache(cache_table)
    get_typhoons(lambda: [], clock=lambda: NOW, cache=cache)
    result = get_typhoons(fetcher, clock=lambda: NOW + 601, cache=cache)
    assert result["meta"]["source"] == "upstream"
    assert result["typhoons"] == TYPHOONS


def test_stale_cache_is_served_when_cwa_fails(cache_table, capsys):
    cache = WeatherCache(cache_table)
    get_typhoons(fetcher, clock=lambda: NOW, cache=cache)
    result = get_typhoons(failing(), clock=lambda: NOW + 3600, cache=cache)
    assert result["meta"]["stale"] is True
    assert result["meta"]["fetched_at"] == 1792148400
    assert "serving_stale_cache" in capsys.readouterr().out


def test_expired_cache_is_not_served(cache_table):
    cache = WeatherCache(cache_table)
    get_typhoons(fetcher, clock=lambda: NOW, cache=cache)
    with pytest.raises(UpstreamError):
        get_typhoons(failing(), clock=lambda: NOW + 86400, cache=cache)


class BrokenCache:
    def get(self, key):
        raise CacheError("get_item failed: timeout")

    def put(self, key, current, fetched_at):
        raise CacheError("put_item failed: timeout")


def test_cache_failure_falls_back_to_cwa(capsys):
    result = get_typhoons(fetcher, clock=lambda: NOW, cache=BrokenCache())
    assert result["meta"]["source"] == "upstream"
    out = capsys.readouterr().out
    assert "cache_read_failed" in out and "cache_write_failed" in out
