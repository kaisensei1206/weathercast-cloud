"""handler：從 API Gateway 事件到 HTTP 回應的完整流程。

事件經過 handler → weather_service → weather_client，只有最底層的 urlopen 是假的，
所以這裡驗證的是「各種上游狀況最後會變成哪個 HTTP 狀態碼」。
"""

import http.client
import json
import urllib.error

import pytest

import handler
from fakes import SAMPLE_CURRENT


class FakeContext:
    aws_request_id = "req-123"


def log_lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


# --- 1. /health ---------------------------------------------------------------


@pytest.mark.parametrize("path", ["/health", "/api/health"])
def test_health(api, path):
    resp = api(path)
    assert resp.status == 200
    assert resp.body == {"status": "ok"}
    assert resp.headers["Content-Type"] == "application/json; charset=utf-8"


def test_cities_lists_all_supported_cities(api):
    resp = api("/api/cities")
    assert resp.status == 200
    assert len(resp.body["cities"]) == 22
    assert {"id": "tainan", "name": "臺南市", "name_en": "Tainan"} in resp.body["cities"]


# --- 2. 天氣查詢成功 ------------------------------------------------------------


def test_weather_success(api, upstream):
    resp = api("/api/weather", {"city": "Tainan"})

    assert resp.status == 200
    assert resp.body["city"] == {"id": "tainan", "name": "臺南市", "name_en": "Tainan"}
    assert resp.body["current"]["temperature"] == SAMPLE_CURRENT["temperature_2m"]
    assert resp.body["current"]["description"] == "大致晴朗"
    assert resp.body["meta"]["source"] == "upstream"
    assert resp.body["meta"]["stale"] is False
    assert len(upstream.calls) == 1


def test_weather_response_keeps_chinese_readable(api, upstream):
    result = handler.lambda_handler(
        {"rawPath": "/api/weather", "queryStringParameters": {"city": "台南"}}, None
    )
    # ensure_ascii=False：回應裡是「臺南市」而不是 臺南市
    assert "臺南市" in result["body"]


# --- 3. 缺少城市參數 ------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        pytest.param(None, id="no-query-string"),
        pytest.param({}, id="empty-query-string"),
        pytest.param({"other": "x"}, id="no-city"),
        pytest.param({"city": ""}, id="empty"),
        pytest.param({"city": "   "}, id="spaces-only"),
    ],
)
def test_missing_city_returns_400(api, upstream, params):
    api("/api/weather", params).assert_error(400, "missing_city")
    assert upstream.calls == []


# --- 4. 城市不存在 --------------------------------------------------------------


def test_unknown_city_returns_404(api, upstream):
    resp = api("/api/weather", {"city": "Tokyo"})
    resp.assert_error(404, "city_not_found")
    assert "Tokyo" in resp.body["message"]
    assert upstream.calls == []


# --- 5. 第三方 API 逾時 ---------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(urllib.error.URLError(TimeoutError("timed out")), id="connect"),
        pytest.param(TimeoutError("timed out"), id="read"),
    ],
)
def test_upstream_timeout_returns_504(api, upstream, exc):
    upstream.raises(exc)
    api("/api/weather", {"city": "Tainan"}).assert_error(504, "upstream_timeout")


# --- 6. 第三方 API 回傳 HTTP 錯誤 ----------------------------------------------


@pytest.mark.parametrize("code", [400, 429, 500, 503])
def test_upstream_http_error_returns_502(api, upstream, code):
    upstream.raises(urllib.error.HTTPError("https://api.open-meteo.com", code, "x", {}, None))
    api("/api/weather", {"city": "Tainan"}).assert_error(502, "upstream_error")


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(urllib.error.URLError(OSError("Name not resolved")), id="dns"),
        pytest.param(http.client.RemoteDisconnected("closed"), id="closed-before-response"),
        pytest.param(http.client.IncompleteRead(b"{"), id="truncated-body"),
    ],
)
def test_upstream_connection_failure_returns_502(api, upstream, exc):
    upstream.raises(exc)
    api("/api/weather", {"city": "Tainan"}).assert_error(502, "upstream_error")


# --- 7. 第三方 API 回傳無效 JSON 或缺少必要欄位 ---------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"<html>Service Unavailable</html>", id="html"),
        pytest.param(b"", id="empty-body"),
        pytest.param({"current": {"time": "2026-10-16T19:45"}}, id="missing-fields"),
        pytest.param({"hourly": {}}, id="no-current"),
    ],
)
def test_invalid_upstream_data_returns_502(api, upstream, payload):
    upstream.returns(payload)
    api("/api/weather", {"city": "Tainan"}).assert_error(502, "upstream_error")


def test_upstream_failure_is_logged(api, upstream, capsys):
    upstream.raises(TimeoutError("timed out"))
    api("/api/weather", {"city": "Tainan"})

    [entry] = log_lines(capsys)
    assert entry["level"] == "warning"
    assert entry["message"] == "upstream_timeout"
    assert entry["city"] == "Tainan"


# --- 8. 城市名稱包含空白或特殊字元 ----------------------------------------------


@pytest.mark.parametrize(
    ("city", "expected_id"),
    [
        ("  Tainan  ", "tainan"),
        ("台 南", "tainan"),
        ("TAINAN", "tainan"),
        ("new-taipei", "new-taipei"),
        ("New Taipei", "new-taipei"),
    ],
)
def test_city_with_spaces_or_symbols_is_normalized(api, upstream, city, expected_id):
    resp = api("/api/weather", {"city": city})
    assert resp.status == 200
    assert resp.body["city"]["id"] == expected_id


@pytest.mark.parametrize(
    "city",
    [
        "<script>alert(1)</script>",
        "Tainan'; DROP TABLE weather;--",
        "../../etc/passwd",
        "%E5%8F%B0%E5%8D%97",
        "🌧️",
        "\x00",
    ],
)
def test_special_characters_are_rejected_safely(api, upstream, city):
    # 白名單外的輸入一律 404，不會送到 Open-Meteo，也不會造成 500
    api("/api/weather", {"city": city}).assert_error(404, "city_not_found")
    assert upstream.calls == []


def test_too_long_city_returns_400(api, upstream):
    api("/api/weather", {"city": "x" * 51}).assert_error(400, "invalid_city")
    assert upstream.calls == []


# --- 9. 未預期例外 -------------------------------------------------------------


def test_unexpected_exception_returns_500_without_details(api, monkeypatch, capsys):
    def boom(query):
        raise RuntimeError("db password=hunter2")

    monkeypatch.setattr(handler, "get_weather", boom)
    resp = api("/api/weather", {"city": "Tainan"}, context=FakeContext())

    resp.assert_error(500, "internal_error")
    assert resp.body["request_id"] == "req-123"
    # 使用者看不到例外內容；完整 traceback 只寫進 log
    assert "hunter2" not in json.dumps(resp.body)
    [entry] = log_lines(capsys)
    assert entry["level"] == "error"
    assert entry["request_id"] == "req-123"
    assert "Traceback" in entry["traceback"]


def test_unexpected_exception_without_lambda_context(api, monkeypatch):
    monkeypatch.setattr(handler, "route", lambda event: 1 / 0)
    resp = api("/api/health")
    resp.assert_error(500, "internal_error")
    assert resp.body["request_id"] == "local"


def test_malformed_event_returns_500_not_crash():
    result = handler.lambda_handler(None, None)
    assert result["statusCode"] == 500
    assert json.loads(result["body"])["error"] == "internal_error"


# --- 其他路由 -----------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_non_get_method_returns_405(api, method):
    api("/api/weather", {"city": "Tainan"}, method=method).assert_error(405, "method_not_allowed")


@pytest.mark.parametrize("path", ["/", "/api", "/api/unknown", "/weather/tainan"])
def test_unknown_path_returns_404(api, path):
    api(path).assert_error(404, "not_found")
