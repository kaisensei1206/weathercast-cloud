"""weather_client：把 Open-Meteo 的各種失敗分成「逾時」與「其他上游錯誤」。

這裡直接把 urlopen 換成假的，所以能模擬真實網路上很難重現的狀況（逾時、斷線、壞掉的 JSON）。
"""

import http.client
import io
import json
import socket
import time
import urllib.error
import urllib.parse

import pytest

import weather_client
from cities import find_city
from fakes import SAMPLE_CURRENT
from weather_client import (
    CURRENT_FIELDS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
    UpstreamBackoff,
    UpstreamError,
    UpstreamTimeout,
    build_url,
    fetch_current,
    parse_current,
)

TAINAN = find_city("Tainan")


def test_build_url_uses_city_coordinates_and_taipei_timezone():
    url = urllib.parse.urlsplit(build_url(TAINAN))
    params = urllib.parse.parse_qs(url.query)

    assert url.netloc == "api.open-meteo.com"
    assert params["latitude"] == [str(TAINAN.lat)]
    assert params["longitude"] == [str(TAINAN.lon)]
    assert params["current"] == [",".join(CURRENT_FIELDS)]
    assert params["timezone"] == ["Asia/Taipei"]


def test_fetch_current_returns_current_block(upstream):
    assert fetch_current(TAINAN) == SAMPLE_CURRENT
    assert len(upstream.calls) == 1
    assert upstream.calls[0]["url"] == build_url(TAINAN)


def test_fetch_current_always_sets_a_timeout(upstream):
    fetch_current(TAINAN)
    assert upstream.calls[0]["timeout"] == DEFAULT_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(urllib.error.URLError(TimeoutError("timed out")), id="connect-timeout"),
        pytest.param(TimeoutError("timed out"), id="read-timeout"),
    ],
)
def test_timeouts_raise_upstream_timeout(upstream, exc):
    upstream.raises(exc)
    with pytest.raises(UpstreamTimeout):
        fetch_current(TAINAN)


@pytest.mark.parametrize("code", [400, 429, 500, 503])
def test_http_error_raises_upstream_error(upstream, code):
    upstream.raises(urllib.error.HTTPError(build_url(TAINAN), code, "error", {}, None))
    with pytest.raises(UpstreamError, match=f"HTTP {code}") as info:
        fetch_current(TAINAN)
    assert not isinstance(info.value, UpstreamTimeout)


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(urllib.error.URLError(socket.gaierror("Name not resolved")), id="dns"),
        pytest.param(urllib.error.URLError(ConnectionRefusedError()), id="refused"),
        # 以下三種發生在「讀取回應」的階段，urllib 不會包成 URLError
        pytest.param(http.client.RemoteDisconnected("closed"), id="closed-before-response"),
        pytest.param(http.client.IncompleteRead(b'{"current":'), id="truncated-body"),
        pytest.param(ConnectionResetError(), id="connection-reset"),
    ],
)
def test_connection_failures_raise_upstream_error(upstream, exc):
    upstream.raises(exc)
    with pytest.raises(UpstreamError) as info:
        fetch_current(TAINAN)
    assert not isinstance(info.value, UpstreamTimeout)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"<html>502 Bad Gateway</html>", id="html"),
        pytest.param(b"", id="empty"),
        pytest.param(b'{"current": ', id="truncated-json"),
        pytest.param(b"\xff\xfe\x00", id="not-utf8"),
    ],
)
def test_invalid_json_raises_upstream_error(upstream, body):
    upstream.returns(body)
    with pytest.raises(UpstreamError, match="invalid JSON"):
        fetch_current(TAINAN)


def without(field):
    return {k: v for k, v in SAMPLE_CURRENT.items() if k != field}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="not-an-object"),
        pytest.param({}, id="no-current"),
        pytest.param({"current": None}, id="current-null"),
        pytest.param({"current": "sunny"}, id="current-string"),
        pytest.param({"current": without("temperature_2m")}, id="missing-temperature"),
        pytest.param({"current": without("weather_code")}, id="missing-weather-code"),
        pytest.param({"current": without("time")}, id="missing-time"),
        pytest.param({"current": {**SAMPLE_CURRENT, "temperature_2m": "27.7"}}, id="number-as-str"),
        pytest.param(
            {"current": {**SAMPLE_CURRENT, "relative_humidity_2m": None}}, id="null-field"
        ),
        pytest.param({"error": True, "reason": "Latitude must be in range"}, id="error-payload"),
    ],
)
def test_missing_or_invalid_fields_raise_upstream_error(upstream, payload):
    upstream.returns(payload)
    with pytest.raises(UpstreamError):
        fetch_current(TAINAN)


def test_parse_current_accepts_integers_and_floats():
    current = {**SAMPLE_CURRENT, "temperature_2m": 28, "precipitation": 1.5}
    assert parse_current({"current": current}) == current


# --- 安全審查後加的回歸測試 -------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"NaN", id="nan"),
        pytest.param(b"Infinity", id="infinity"),
        pytest.param(b"-Infinity", id="minus-infinity"),
        pytest.param(b"1e999", id="overflow-to-inf"),
        pytest.param(b"true", id="bool"),
    ],
)
def test_non_finite_or_boolean_numbers_are_rejected(upstream, raw):
    # NaN/Infinity 不是合法 JSON，回給瀏覽器會解析失敗，也不能寫進快取
    body = json.dumps({"current": SAMPLE_CURRENT}).replace("27.7", "@").encode()
    upstream.returns(body.replace(b"@", raw))
    with pytest.raises(UpstreamError):
        fetch_current(TAINAN)


def test_oversized_response_is_rejected(upstream):
    upstream.returns(b" " * (MAX_RESPONSE_BYTES + 1))
    with pytest.raises(UpstreamError, match="too large"):
        fetch_current(TAINAN)


def test_slow_upstream_is_cut_off_at_the_total_deadline(monkeypatch):
    # urllib 的 timeout 只限制每次讀取；上游一直慢慢送資料時，靠總時限結束
    def slow_urlopen(url, timeout=None):
        time.sleep(1.0)
        return io.BytesIO(json.dumps({"current": SAMPLE_CURRENT}).encode())

    monkeypatch.setattr(weather_client.urllib.request, "urlopen", slow_urlopen)
    started = time.monotonic()
    with pytest.raises(UpstreamTimeout, match="deadline"):
        fetch_current(TAINAN, deadline=0.2)
    assert time.monotonic() - started < 0.8


def test_backoff_skips_the_upstream_for_a_while_after_a_failure():
    clock = [1000.0]
    backoff = UpstreamBackoff(seconds=30, monotonic=lambda: clock[0])
    calls = []

    def failing():
        calls.append(1)
        raise UpstreamTimeout("read timeout")

    for _ in range(5):
        with pytest.raises(UpstreamError):
            backoff.call(failing)
    assert len(calls) == 1  # 後面 4 次沒有真的呼叫上游

    clock[0] += 30
    assert backoff.call(lambda: "ok") == "ok"  # 時間到了就重新嘗試
