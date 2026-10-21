"""颱風資料的業務邏輯：快取與舊資料備援，流程和 weather_service 相同。

颱風資料和天氣共用同一張 DynamoDB 快取表，用固定的 key "typhoons:cwa"
（不會和城市 ID 撞名）。氣象署每 3 到 6 小時才更新一次颱風路徑，
快取 10 分鐘可以讓大部分請求不必呼叫氣象署，也不容易用完授權碼的呼叫額度。
"""

import time
from collections.abc import Callable

from logger import log
from typhoon_client import fetch_typhoons
from weather_cache import CacheError, WeatherCache
from weather_client import UpstreamError

CACHE_KEY = "typhoons:cwa"


def build_response(typhoons: list[dict], fetched_at: int, source: str, stale: bool) -> dict:
    return {
        "typhoons": typhoons,
        "meta": {
            "source": source,
            "stale": stale,
            "fetched_at": fetched_at,
            "provider": "cwa",
        },
    }


def get_typhoons(
    fetcher: Callable[[], list[dict]] = fetch_typhoons,
    clock: Callable[[], float] = time.time,
    cache: WeatherCache | None = None,
) -> dict:
    now = int(clock())

    cached = None
    if cache is not None:
        try:
            cached = cache.get(CACHE_KEY)
        except CacheError as exc:
            log("error", "cache_read_failed", key=CACHE_KEY, detail=str(exc))
        if cached is not None and cached.is_expired(now):
            cached = None

    if cached is not None and cached.is_fresh(now):
        return build_response(cached.current["typhoons"], cached.fetched_at, "cache", stale=False)

    try:
        typhoons = fetcher()
    except UpstreamError as exc:
        if cached is None:
            raise
        log("warning", "serving_stale_cache", key=CACHE_KEY, detail=str(exc))
        return build_response(cached.current["typhoons"], cached.fetched_at, "cache", stale=True)

    if cache is not None:
        try:
            cache.put(CACHE_KEY, {"typhoons": typhoons}, now)
        except CacheError as exc:
            log("error", "cache_write_failed", key=CACHE_KEY, detail=str(exc))
    return build_response(typhoons, now, "upstream", stale=False)
