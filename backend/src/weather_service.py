"""天氣查詢的業務邏輯，和 HTTP／Lambda 無關。

handler.py 負責把 HTTP 請求轉成這裡的函式呼叫，再把結果或例外轉成 HTTP 回應。
分開之後，業務邏輯可以直接用一般函式測試，不用組 API Gateway 事件。

查詢流程（cache 為 None 時跳過所有快取步驟）：
1. 驗證輸入，無效就直接丟例外，不讀快取也不呼叫 Open-Meteo
2. 快取還新鮮（Cache Hit）→ 直接回傳
3. 否則呼叫 Open-Meteo（Cache Miss）→ 成功就寫回快取
4. Open-Meteo 失敗但有未超過保留期限的舊資料 → 回傳舊資料並標示 stale
快取讀寫失敗只記 log，當作沒有快取繼續處理（fail-open）。
"""

import time
from collections.abc import Callable

from cities import City, find_city
from logger import log
from weather_cache import CacheEntry, CacheError, WeatherCache
from weather_client import UpstreamError, fetch_current

MAX_CITY_LENGTH = 50

# WMO weather code → 中文描述
WEATHER_DESCRIPTIONS = {
    0: "晴",
    1: "大致晴朗",
    2: "多雲",
    3: "陰",
    45: "霧",
    48: "霧淞",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    80: "陣雨",
    81: "陣雨",
    82: "強陣雨",
    95: "雷雨",
    96: "雷雨伴隨冰雹",
    99: "雷雨伴隨冰雹",
}


class MissingCity(Exception):
    pass


class InvalidCity(Exception):
    pass


class CityNotFound(Exception):
    def __init__(self, query: str):
        super().__init__(query)
        self.query = query


def describe(code: int) -> str:
    return WEATHER_DESCRIPTIONS.get(code, "未知")


def resolve_city(query: str | None) -> City:
    query = (query or "").strip()
    if not query:
        raise MissingCity()
    if len(query) > MAX_CITY_LENGTH:
        raise InvalidCity()
    city = find_city(query)
    if city is None:
        raise CityNotFound(query)
    return city


def to_api_current(raw: dict) -> dict:
    """把 Open-Meteo 的欄位名稱轉成本服務的格式。快取裡存的也是這個格式。"""
    return {
        "time": raw["time"],
        "temperature": raw["temperature_2m"],
        "apparent_temperature": raw["apparent_temperature"],
        "humidity": raw["relative_humidity_2m"],
        "precipitation": raw["precipitation"],
        "wind_speed": raw["wind_speed_10m"],
        "weather_code": raw["weather_code"],
        "description": describe(raw["weather_code"]),
    }


def build_response(city: City, current: dict, fetched_at: int, source: str, stale: bool) -> dict:
    return {
        "city": {"id": city.id, "name": city.name_zh, "name_en": city.name_en},
        "current": current,
        "meta": {
            "source": source,
            "stale": stale,
            "fetched_at": fetched_at,
            "provider": "open-meteo",
        },
    }


def read_cache(cache: WeatherCache | None, city: City, now: int) -> CacheEntry | None:
    """回傳還在保留期限內的快取；沒有、已超過保留期限、或讀取失敗都回傳 None。"""
    if cache is None:
        return None
    try:
        entry = cache.get(city.id)
    except CacheError as exc:
        log("error", "cache_read_failed", city=city.id, detail=str(exc))
        return None
    if entry is None or entry.is_expired(now):
        return None
    return entry


def write_cache(cache: WeatherCache | None, city: City, current: dict, now: int) -> None:
    if cache is None:
        return
    try:
        cache.put(city.id, current, now)
    except CacheError as exc:
        log("error", "cache_write_failed", city=city.id, detail=str(exc))


def get_weather(
    query: str | None,
    fetcher: Callable[[City], dict] = fetch_current,
    clock: Callable[[], float] = time.time,
    cache: WeatherCache | None = None,
) -> dict:
    """查詢城市目前天氣。fetcher、clock、cache 都可替換，方便測試時不呼叫真實 API 和 AWS。"""
    city = resolve_city(query)
    now = int(clock())

    cached = read_cache(cache, city, now)
    if cached is not None and cached.is_fresh(now):
        return build_response(city, cached.current, cached.fetched_at, "cache", stale=False)

    try:
        current = to_api_current(fetcher(city))
    except UpstreamError as exc:
        if cached is None:
            raise
        log(
            "warning",
            "serving_stale_cache",
            city=city.id,
            fetched_at=cached.fetched_at,
            detail=str(exc),
        )
        return build_response(city, cached.current, cached.fetched_at, "cache", stale=True)

    write_cache(cache, city, current, now)
    return build_response(city, current, now, "upstream", stale=False)
