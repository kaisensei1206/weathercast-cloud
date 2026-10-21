"""typhoon_client：取得金鑰、呼叫氣象署、把回應整理成本服務的格式。

urlopen 換成假的（`cwa` fixture），SSM 用 moto 在記憶體裡模擬，都不連網路。
"""

import copy
import http.client
import urllib.error
import urllib.parse

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from moto import mock_aws

import typhoon_client
from fakes import SAMPLE_CWA
from typhoon_client import (
    DEFAULT_TIMEOUT_SECONDS,
    TyphoonNotConfigured,
    api_key,
    build_url,
    fetch_typhoons,
    parse_typhoon,
    parse_typhoons,
)
from weather_client import UpstreamError, UpstreamTimeout

PARAM = "/weathercast/cwa-api-key"


def cyclone():
    return copy.deepcopy(SAMPLE_CWA["records"]["tropicalCyclones"]["tropicalCyclone"][0])


# --- 金鑰 ---------------------------------------------------------------------


@pytest.fixture
def ssm():
    with mock_aws():
        yield boto3.client("ssm")


def test_key_from_environment_skips_ssm():
    assert api_key({"CWA_API_KEY": " abc ", "CWA_API_KEY_PARAM": PARAM}, ssm=object()) == "abc"


def test_key_is_read_from_ssm_secure_string(ssm):
    ssm.put_parameter(Name=PARAM, Value="secret-key", Type="SecureString")
    assert api_key({"CWA_API_KEY_PARAM": PARAM}, ssm=ssm) == "secret-key"


def test_key_is_read_from_ssm_only_once(ssm):
    ssm.put_parameter(Name=PARAM, Value="first", Type="SecureString")
    api_key({"CWA_API_KEY_PARAM": PARAM}, ssm=ssm)
    ssm.put_parameter(Name=PARAM, Value="second", Type="SecureString", Overwrite=True)
    assert api_key({"CWA_API_KEY_PARAM": PARAM}, ssm=ssm) == "first"


def test_default_ssm_client_is_created_when_not_given(ssm):
    ssm.put_parameter(Name=PARAM, Value="secret-key", Type="SecureString")
    assert api_key({"CWA_API_KEY_PARAM": PARAM}) == "secret-key"


def test_no_setting_means_not_configured():
    with pytest.raises(TyphoonNotConfigured):
        api_key({})


def test_missing_parameter_means_not_configured_and_is_not_cached(ssm):
    with pytest.raises(TyphoonNotConfigured, match=PARAM):
        api_key({"CWA_API_KEY_PARAM": PARAM}, ssm=ssm)
    # 之後才把金鑰存進 SSM，不用重新部署就能生效
    ssm.put_parameter(Name=PARAM, Value="later", Type="SecureString")
    assert api_key({"CWA_API_KEY_PARAM": PARAM}, ssm=ssm) == "later"


class RaisingSsm:
    def __init__(self, exc):
        self.exc = exc

    def get_parameter(self, **kwargs):
        raise self.exc


def test_access_denied_is_upstream_error_not_disabled():
    # 例如 IAM 權限少了 ssm:GetParameter：這是設定錯誤，要讓 log 看得到，不是「功能停用」
    denied = ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetParameter")
    with pytest.raises(UpstreamError, match="AccessDenied"):
        api_key({"CWA_API_KEY_PARAM": PARAM}, ssm=RaisingSsm(denied))


def test_ssm_connection_failure_is_upstream_error():
    broken = RaisingSsm(EndpointConnectionError(endpoint_url="https://ssm"))
    with pytest.raises(UpstreamError, match="SSM"):
        api_key({"CWA_API_KEY_PARAM": PARAM}, ssm=broken)


# --- 呼叫氣象署 -----------------------------------------------------------------


def test_build_url_asks_for_json_with_key():
    url = urllib.parse.urlsplit(build_url("k&y"))
    assert url.netloc == "opendata.cwa.gov.tw"
    assert url.path.endswith("/W-C0034-005")
    assert urllib.parse.parse_qs(url.query) == {"Authorization": ["k&y"], "format": ["JSON"]}


def test_fetch_typhoons_parses_response_with_timeout(cwa):
    typhoons = fetch_typhoons()
    assert [t["name"] for t in typhoons] == ["鳳凰"]
    assert cwa.calls == [{"url": build_url("test-key"), "timeout": DEFAULT_TIMEOUT_SECONDS}]


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(urllib.error.URLError(TimeoutError("timed out")), id="connect-timeout"),
        pytest.param(TimeoutError("timed out"), id="read-timeout"),
    ],
)
def test_timeouts_raise_upstream_timeout(cwa, exc):
    cwa.raises(exc)
    with pytest.raises(UpstreamTimeout):
        fetch_typhoons()


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(urllib.error.HTTPError(build_url("test-key"), 401, "x", {}, None), id="401"),
        pytest.param(urllib.error.URLError(ConnectionRefusedError()), id="refused"),
        pytest.param(http.client.RemoteDisconnected("closed"), id="closed"),
        pytest.param(ConnectionResetError(), id="reset"),
    ],
)
def test_connection_errors_never_leak_the_key(cwa, exc):
    cwa.raises(exc)
    with pytest.raises(UpstreamError) as info:
        fetch_typhoons()
    assert not isinstance(info.value, UpstreamTimeout)
    assert "test-key" not in str(info.value)


@pytest.mark.parametrize("body", [b"<html>", b"\xff\xfe"])
def test_invalid_body_is_upstream_error(cwa, body):
    cwa.returns(body)
    with pytest.raises(UpstreamError, match="invalid JSON"):
        fetch_typhoons()


# --- 整理格式 -------------------------------------------------------------------


def test_parse_typhoon_maps_track_current_and_forecast():
    result = parse_typhoon(cyclone())

    assert result["name"] == "鳳凰"
    assert result["name_en"] == "FUNG-WONG"
    assert result["number"] == "26"
    assert result["track"] == [
        {"time": "2026-10-20T08:00:00+08:00", "lat": 18.5, "lon": 128.0},
        {"time": "2026-10-20T14:00:00+08:00", "lat": 19.0, "lon": 127.0},
    ]
    assert result["current"] == {
        "time": "2026-10-20T14:00:00+08:00",
        "lat": 19.0,
        "lon": 127.0,
        "max_wind_ms": 38.0,
        "max_gust_ms": 48.0,
        "pressure_hpa": 955.0,
        "moving_speed_kmh": 20.0,
        "moving_direction": "WNW",
        "radius_15ms_km": 250.0,
    }
    first, second = result["forecast"]
    assert first == {
        "time": "2026-10-21T14:00:00+08:00",  # 發布時間 + 24 小時
        "lat": 20.5,
        "lon": 124.5,
        "max_wind_ms": 43.0,
        "max_gust_ms": 53.0,
        "pressure_hpa": 945.0,
        "tau_hours": 24.0,
        "radius_70pct_km": 120.0,
    }
    assert second["time"] == "2026-10-22T14:00:00+08:00"
    assert second["max_gust_ms"] is None  # 缺欄位是 None，不是錯誤


def test_tropical_depression_without_name_gets_generic_name():
    raw = cyclone()
    for key in ("cwaTyphoonName", "typhoonName", "cwaTyNo"):
        del raw[key]
    raw["cwaTdNo"] = "05"
    result = parse_typhoon(raw)
    assert result["name"] == "熱帶性低氣壓"
    assert result["number"] == "05"


def test_single_fix_object_is_accepted_as_a_list():
    raw = cyclone()
    raw["analysisData"]["fix"] = raw["analysisData"]["fix"][0]
    raw["forecastData"] = {"fix": raw["forecastData"]["fix"][0]}
    result = parse_typhoon(raw)
    assert len(result["track"]) == 1
    assert len(result["forecast"]) == 1


@pytest.mark.parametrize(
    "coordinate",
    [None, 121.5, "121.5", "abc,def", "121.5,95", "400,20", "nan,20"],
)
def test_bad_coordinates_are_skipped(coordinate):
    raw = cyclone()
    raw["analysisData"]["fix"][0]["coordinate"] = coordinate
    raw["forecastData"]["fix"][0]["coordinate"] = coordinate
    result = parse_typhoon(raw)
    assert len(result["track"]) == 1
    assert len(result["forecast"]) == 1


def test_cyclone_without_any_position_is_dropped():
    raw = cyclone()
    raw["analysisData"] = {"fix": [{"coordinate": "bad"}, "not a dict"]}
    assert parse_typhoon(raw) is None


@pytest.mark.parametrize(
    ("init_time", "tau"),
    [(None, "24"), ("2026-10-20T14:00:00+08:00", None), ("not a time", "24")],
)
def test_forecast_time_is_none_when_it_cannot_be_computed(init_time, tau):
    raw = cyclone()
    raw["forecastData"]["fix"][0].update(initTime=init_time, tau=tau)
    assert parse_typhoon(raw)["forecast"][0]["time"] is None


def test_radius_can_be_a_plain_number():
    raw = cyclone()
    raw["analysisData"]["fix"][-1]["circleOf15Ms"] = "180"
    assert parse_typhoon(raw)["current"]["radius_15ms_km"] == 180.0


def test_parse_typhoons_returns_all_valid_cyclones():
    data = copy.deepcopy(SAMPLE_CWA)
    bad = {"analysisData": {"fix": []}}
    data["records"]["tropicalCyclones"]["tropicalCyclone"] += [bad, "junk"]
    assert [t["name"] for t in parse_typhoons(data)] == ["鳳凰"]


def test_single_cyclone_object_is_accepted_as_a_list():
    data = copy.deepcopy(SAMPLE_CWA)
    data["records"]["tropicalCyclones"]["tropicalCyclone"] = cyclone()
    assert len(parse_typhoons(data)) == 1


@pytest.mark.parametrize(
    "records",
    [{}, {"tropicalCyclones": None}, {"tropicalCyclones": {"tropicalCyclone": []}}],
)
def test_no_typhoon_is_an_empty_list_not_an_error(records):
    assert parse_typhoons({"success": "true", "records": records}) == []


@pytest.mark.parametrize(
    "data",
    [
        pytest.param([], id="not-object"),
        pytest.param({"success": "false", "records": {}}, id="not-success"),
        pytest.param({"success": "true"}, id="no-records"),
        pytest.param(
            {"success": "true", "records": {"tropicalCyclones": {"tropicalCyclone": "x"}}},
            id="cyclones-not-list",
        ),
    ],
)
def test_wrong_structure_is_upstream_error(data):
    with pytest.raises(UpstreamError):
        parse_typhoons(data)


def test_module_cache_is_reset_between_tests():
    assert typhoon_client._cached_key is None
