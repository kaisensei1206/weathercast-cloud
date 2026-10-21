"""fireworks_client：下載觀光署的活動 zip、挑出煙火相關活動、整理格式。

urlopen 換成假的（`tourism` fixture），zip 在測試裡現場組出來，不連網路。
"""

import copy
import http.client
import urllib.error

import pytest

import fireworks_client
from fakes import SAMPLE_EVENT, event_list, tourism_zip
from fireworks_client import (
    DEFAULT_TIMEOUT_SECONDS,
    EVENTS_URL,
    classify,
    fetch_events,
    parse_event,
    parse_events,
    read_event_list,
)
from weather_client import UpstreamError, UpstreamTimeout


def event(**changes):
    raw = copy.deepcopy(SAMPLE_EVENT)
    raw.update(changes)
    return raw


def test_fetch_events_downloads_zip_with_timeout(tourism):
    events = fetch_events()

    assert tourism.calls == [{"url": EVENTS_URL, "timeout": DEFAULT_TIMEOUT_SECONDS}]
    assert events == [
        {
            "id": "Event_376540000A_006236",
            "name": "2026成功鎮花火之夜",
            "kind": "fireworks",
            "start": "2026-02-16T21:00:00+08:00",
            "end": "2026-02-16T23:59:59+08:00",
            "city": "臺東縣",
            "town": "成功鎮",
            "address": "海濱公園",
            "lat": 23.10404,
            "lon": 121.38497,
            "url": None,
            "image": "https://tour.taitung.gov.tw/image/54819/640x480",
            "organizer": None,
        }
    ]


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(urllib.error.URLError(TimeoutError("timed out")), id="connect-timeout"),
        pytest.param(TimeoutError("timed out"), id="read-timeout"),
    ],
)
def test_timeouts_raise_upstream_timeout(tourism, exc):
    tourism.raises(exc)
    with pytest.raises(UpstreamTimeout):
        fetch_events()


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(urllib.error.HTTPError(EVENTS_URL, 404, "x", {}, None), id="404"),
        pytest.param(urllib.error.URLError(ConnectionRefusedError()), id="refused"),
        pytest.param(http.client.IncompleteRead(b"PK"), id="truncated"),
        pytest.param(ConnectionResetError(), id="reset"),
    ],
)
def test_connection_errors_raise_upstream_error(tourism, exc):
    tourism.raises(exc)
    with pytest.raises(UpstreamError) as info:
        fetch_events()
    assert not isinstance(info.value, UpstreamTimeout)


def test_oversized_download_is_rejected(tourism, monkeypatch):
    monkeypatch.setattr(fireworks_client, "MAX_ZIP_BYTES", 100)
    with pytest.raises(UpstreamError, match="too large"):
        fetch_events()


def test_oversized_json_inside_zip_is_rejected(monkeypatch):
    # 解壓縮前先看 zip 標示的大小，不會真的把巨大的檔案解開（防 zip bomb）
    monkeypatch.setattr(fireworks_client, "MAX_JSON_BYTES", 10)
    with pytest.raises(UpstreamError, match="too large"):
        read_event_list(tourism_zip(event_list(SAMPLE_EVENT)))


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"<html>not a zip</html>", id="not-zip"),
        pytest.param(tourism_zip(event_list(), name="Other.json"), id="missing-file"),
        pytest.param(tourism_zip(b"{broken"), id="bad-json"),
        pytest.param(tourism_zip(b"\xff\xfe"), id="bad-encoding"),
    ],
)
def test_invalid_zip_content_is_upstream_error(body):
    with pytest.raises(UpstreamError):
        read_event_list(body)


def test_bom_is_removed():
    assert read_event_list(tourism_zip(event_list()))["Events"] == []


@pytest.mark.parametrize(
    ("name", "description", "kind"),
    [
        ("2026成功鎮花火之夜", "", "fireworks"),
        ("國慶焰火", "", "fireworks"),
        ("跨年烟火秀", "", "fireworks"),
        ("大稻埕夏日節", "最後一晚有煙火", "maybe"),
        ("咖啡節", "手沖咖啡體驗", None),
    ],
)
def test_classify(name, description, kind):
    assert classify(name, description) == kind


def test_event_only_mentioning_fireworks_is_maybe():
    result = parse_event(event(EventName="2026大稻埕夏日節", Description="閉幕施放煙火"))
    assert result["kind"] == "maybe"


def test_optional_fields_are_filled_when_present():
    result = parse_event(
        event(
            WebsiteURL=" https://example.gov.tw/event ",
            Organizations=[{"Name": ""}, {"Name": "交通部觀光署"}],
            Images="not a list",
            PostalAddress=None,
            EndDateTime=None,
        )
    )
    assert result["url"] == "https://example.gov.tw/event"
    assert result["organizer"] == "交通部觀光署"
    assert result["image"] is None
    assert (result["city"], result["town"], result["address"]) == ("", "", "")
    assert result["end"] == result["start"]  # 沒有結束時間就當作同一個時間點


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"EventName": "咖啡節", "Description": "咖啡"}, id="not-fireworks"),
        pytest.param({"EventName": "  "}, id="no-name"),
        pytest.param({"EventStatus": "EventCancelled"}, id="cancelled"),
        pytest.param({"StartDateTime": "2026/2/16"}, id="bad-start"),
        pytest.param({"StartDateTime": None}, id="no-start"),
        pytest.param({"PositionLat": None}, id="no-lat"),
        pytest.param({"PositionLon": "121.3"}, id="string-lon"),
        pytest.param({"PositionLat": True}, id="bool-lat"),
        pytest.param({"PositionLat": 123.0}, id="lat-out-of-range"),
    ],
)
def test_unusable_events_are_skipped(changes):
    assert parse_event(event(**changes)) is None


def test_parse_events_sorts_dedupes_and_skips_junk():
    later = event(
        EventID="b", EventName="日月潭花火音樂嘉年華", StartDateTime="2026-09-12T00:00:00+08:00"
    )
    duplicate = event(
        EventID="c", EventName="日月潭 花火音樂嘉年華", StartDateTime="2026-09-12T17:12:00+08:00"
    )
    data = event_list(
        later, "junk", duplicate, SAMPLE_EVENT, event(EventName="咖啡節", Description="")
    )

    assert [e["id"] for e in parse_events(data)] == ["Event_376540000A_006236", "b"]


@pytest.mark.parametrize("data", [[], {"Events": None}, {"Events": "x"}])
def test_wrong_structure_is_upstream_error(data):
    with pytest.raises(UpstreamError, match="Events"):
        parse_events(data)
