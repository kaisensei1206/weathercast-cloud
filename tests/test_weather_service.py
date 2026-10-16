"""weather_service：輸入驗證與回應格式。

get_weather 的 fetcher 和 clock 可以替換（依賴注入），所以這裡完全不碰網路，也不用 mock urllib。
"""

import pytest

from fakes import SAMPLE_CURRENT
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
