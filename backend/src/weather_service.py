"""天氣查詢的業務邏輯，和 HTTP／Lambda 無關。

handler.py 負責把 HTTP 請求轉成這裡的函式呼叫，再把結果或例外轉成 HTTP 回應。
分開之後，業務邏輯可以直接用一般函式測試，不用組 API Gateway 事件。
"""

import time
from collections.abc import Callable

from cities import City, find_city
from weather_client import fetch_current

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


def get_weather(
    query: str | None,
    fetcher: Callable[[City], dict] = fetch_current,
    clock: Callable[[], float] = time.time,
) -> dict:
    """查詢城市目前天氣。fetcher 與 clock 可替換，方便測試時不呼叫真實 API。"""
    city = resolve_city(query)
    current = fetcher(city)
    return {
        "city": {"id": city.id, "name": city.name_zh, "name_en": city.name_en},
        "current": {
            "time": current["time"],
            "temperature": current["temperature_2m"],
            "apparent_temperature": current["apparent_temperature"],
            "humidity": current["relative_humidity_2m"],
            "precipitation": current["precipitation"],
            "wind_speed": current["wind_speed_10m"],
            "weather_code": current["weather_code"],
            "description": describe(current["weather_code"]),
        },
        "meta": {
            "source": "upstream",
            "stale": False,
            "fetched_at": int(clock()),
            "provider": "open-meteo",
        },
    }
