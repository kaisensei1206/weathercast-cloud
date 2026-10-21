"""煙火活動的業務邏輯：快取、舊資料備援、只回傳今年的活動。

流程和 weather_service 相同，和天氣共用同一張 DynamoDB 快取表，用固定的 key
"fireworks:tourism"（不會和城市 ID 撞名）。快取存的是所有年份的煙火活動，
「今年」在回應時才依臺灣時間過濾，跨年那一刻不會拿到去年的快取結果。
"""

import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fireworks_client import fetch_events
from logger import log
from weather_cache import CacheError, WeatherCache
from weather_client import UpstreamBackoff, UpstreamError

CACHE_KEY = "fireworks:tourism"
# 觀光署失敗後暫停下載一段時間，和天氣的 BACKOFF 分開計算
BACKOFF = UpstreamBackoff()
# 臺灣沒有日光節約時間，固定 UTC+8；不用 zoneinfo，就不必依賴執行環境的時區資料庫
TAIPEI = timezone(timedelta(hours=8))


def this_year(now: float) -> int:
    return datetime.fromtimestamp(now, TAIPEI).year


def in_year(event: dict, year: int) -> bool:
    """活動期間和這一年有重疊就算，例如 2025-12-31 開始的跨年活動也算 2026 年。"""
    return int(event["start"][:4]) <= year <= int(event["end"][:4])


def build_response(events: list[dict], year: int, fetched_at: int, source: str, stale: bool):
    return {
        "year": year,
        "events": [e for e in events if in_year(e, year)],
        "meta": {
            "source": source,
            "stale": stale,
            "fetched_at": fetched_at,
            "provider": "taiwan-tourism",
        },
    }


def get_fireworks(
    fetcher: Callable[[], list[dict]] = fetch_events,
    clock: Callable[[], float] = time.time,
    cache: WeatherCache | None = None,
    backoff: UpstreamBackoff = BACKOFF,
) -> dict:
    now = clock()
    year, now = this_year(now), int(now)

    cached = None
    if cache is not None:
        try:
            cached = cache.get(CACHE_KEY)
        except CacheError as exc:
            log("error", "cache_read_failed", key=CACHE_KEY, detail=str(exc))
        if cached is not None and cached.is_expired(now):
            cached = None

    if cached is not None and cached.is_fresh(now):
        return build_response(cached.current["events"], year, cached.fetched_at, "cache", False)

    try:
        events = backoff.call(fetcher)
    except UpstreamError as exc:
        if cached is None:
            raise
        log("warning", "serving_stale_cache", key=CACHE_KEY, detail=str(exc))
        return build_response(cached.current["events"], year, cached.fetched_at, "cache", True)

    if cache is not None:
        try:
            cache.put(CACHE_KEY, {"events": events}, now)
        except CacheError as exc:
            log("error", "cache_write_failed", key=CACHE_KEY, detail=str(exc))
    return build_response(events, year, now, "upstream", stale=False)
