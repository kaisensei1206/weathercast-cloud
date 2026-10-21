"""fireworks_service：只回傳今年（臺灣時間）的活動，快取流程和天氣相同。"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from fireworks_service import CACHE_KEY, get_fireworks, in_year, this_year
from weather_cache import CacheError, WeatherCache
from weather_client import UpstreamBackoff, UpstreamError

TAIPEI = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 21, 17, 0, tzinfo=TAIPEI).timestamp()


def make(name, start, end=None):
    return {"name": name, "start": start, "end": end or start}


EVENTS = [
    make("2025煙火", "2025-07-01T20:00:00+08:00"),
    make("跨年煙火", "2025-12-31T18:00:00+08:00", "2026-01-01T01:00:00+08:00"),
    make("成功鎮花火之夜", "2026-02-16T21:00:00+08:00"),
    make("2027煙火", "2027-01-01T00:00:00+08:00"),
]


def fetcher():
    return EVENTS


def failing():
    raise UpstreamError("tourism HTTP 500")


def must_not_fetch():
    pytest.fail("快取還新鮮時不應該下載觀光署資料")


def test_year_is_taiwan_time():
    # UTC 2025-12-31 16:00 已經是臺灣的 2026-01-01 00:00
    assert this_year(datetime(2025, 12, 31, 16, 0, tzinfo=UTC).timestamp()) == 2026


def test_event_overlapping_the_year_counts():
    assert in_year(EVENTS[1], 2025) and in_year(EVENTS[1], 2026)
    assert not in_year(EVENTS[0], 2026)


def test_only_this_years_events_are_returned():
    result = get_fireworks(fetcher, clock=lambda: NOW)
    assert result["year"] == 2026
    assert [e["name"] for e in result["events"]] == ["跨年煙火", "成功鎮花火之夜"]
    assert result["meta"] == {
        "source": "upstream",
        "stale": False,
        "fetched_at": int(NOW),
        "provider": "taiwan-tourism",
    }


def test_upstream_error_without_cache_is_raised():
    with pytest.raises(UpstreamError):
        get_fireworks(failing, clock=lambda: NOW)


def test_fresh_cache_is_used_and_shares_table(cache_table):
    cache = WeatherCache(cache_table)
    get_fireworks(fetcher, clock=lambda: NOW, cache=cache)
    result = get_fireworks(must_not_fetch, clock=lambda: NOW + 60, cache=cache)
    assert result["meta"]["source"] == "cache"
    assert len(result["events"]) == 2
    assert [i["city_id"] for i in cache_table.scan()["Items"]] == [CACHE_KEY]


def test_cached_events_are_filtered_by_the_current_year(cache_table):
    # 快取存全部年份；跨年後同一份快取要改回傳新的一年
    cache = WeatherCache(cache_table)
    new_year = datetime(2027, 1, 1, 0, 1, tzinfo=TAIPEI).timestamp()
    get_fireworks(fetcher, clock=lambda: new_year - 120, cache=cache)
    result = get_fireworks(must_not_fetch, clock=lambda: new_year, cache=cache)
    assert result["year"] == 2027
    assert [e["name"] for e in result["events"]] == ["2027煙火"]


def test_stale_cache_is_served_when_tourism_fails(cache_table, capsys):
    cache = WeatherCache(cache_table)
    get_fireworks(fetcher, clock=lambda: NOW, cache=cache)
    result = get_fireworks(failing, clock=lambda: NOW + 3600, cache=cache)
    assert result["meta"]["stale"] is True
    assert "serving_stale_cache" in capsys.readouterr().out


def test_expired_cache_is_not_served(cache_table):
    cache = WeatherCache(cache_table)
    get_fireworks(fetcher, clock=lambda: NOW, cache=cache)
    with pytest.raises(UpstreamError):
        get_fireworks(failing, clock=lambda: NOW + 86400, cache=cache)


def test_old_cache_is_refreshed(cache_table):
    cache = WeatherCache(cache_table)
    get_fireworks(lambda: [], clock=lambda: NOW, cache=cache)
    result = get_fireworks(fetcher, clock=lambda: NOW + 601, cache=cache)
    assert result["meta"]["source"] == "upstream"
    assert len(result["events"]) == 2


class BrokenCache:
    def get(self, key):
        raise CacheError("get_item failed: timeout")

    def put(self, key, current, fetched_at):
        raise CacheError("put_item failed: timeout")


def test_cache_failure_falls_back_to_tourism(capsys):
    result = get_fireworks(fetcher, clock=lambda: NOW, cache=BrokenCache())
    assert result["meta"]["source"] == "upstream"
    out = capsys.readouterr().out
    assert "cache_read_failed" in out and "cache_write_failed" in out


def test_failing_tourism_is_not_retried_on_every_request(cache_table):
    cache = WeatherCache(cache_table)
    get_fireworks(fetcher, clock=lambda: NOW, cache=cache)
    calls = []

    def counting_failure():
        calls.append(1)
        failing()

    backoff = UpstreamBackoff()
    for _ in range(10):
        result = get_fireworks(
            counting_failure, clock=lambda: NOW + 3600, cache=cache, backoff=backoff
        )
        assert result["meta"]["stale"] is True
    assert len(calls) == 1
