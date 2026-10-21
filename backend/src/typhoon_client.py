"""中央氣象署開放資料：颱風（熱帶氣旋）路徑，資料集 W-C0034-005。

只負責「取得金鑰、送出 HTTP 請求、把回應整理成本服務的格式」。
和 weather_client 一樣只用標準函式庫 urllib；讀 SSM 用 Lambda 內建的 boto3。

金鑰（授權碼）不寫在程式碼或 Terraform 裡：
- 存在 SSM Parameter Store 的 SecureString，Lambda 只拿到參數「名稱」
  （環境變數 CWA_API_KEY_PARAM），執行時才讀取並解密，同一個執行環境只讀一次。
- 本機測試可以改用環境變數 CWA_API_KEY 直接提供金鑰。
"""

import http.client
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timedelta

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from weather_client import UpstreamError, UpstreamTimeout

TYPHOON_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0034-005"
DEFAULT_TIMEOUT_SECONDS = 3.0

SSM_CONFIG = Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 2})


class TyphoonNotConfigured(Exception):
    """沒有設定氣象署的金鑰，颱風功能停用。"""


_cached_key: str | None = None


def api_key(env: Mapping[str, str] = os.environ, ssm=None) -> str:
    """取得氣象署授權碼；讀過一次就留在記憶體，同一個 Lambda 執行環境不再呼叫 SSM。"""
    global _cached_key
    if _cached_key:
        return _cached_key

    direct = env.get("CWA_API_KEY", "").strip()
    if direct:
        _cached_key = direct
        return direct

    name = env.get("CWA_API_KEY_PARAM", "").strip()
    if not name:
        raise TyphoonNotConfigured("CWA_API_KEY_PARAM is not set")
    try:
        client = ssm or boto3.client("ssm", config=SSM_CONFIG)
        value = client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ParameterNotFound":
            raise TyphoonNotConfigured(f"SSM parameter {name} not found") from exc
        raise UpstreamError(f"SSM get_parameter failed: {exc}") from exc
    except BotoCoreError as exc:
        raise UpstreamError(f"SSM get_parameter failed: {exc}") from exc

    _cached_key = value.strip()
    return _cached_key


def reset_key_cache() -> None:
    """測試用：清掉記憶體裡的金鑰。"""
    global _cached_key
    _cached_key = None


def build_url(key: str) -> str:
    return f"{TYPHOON_URL}?{urllib.parse.urlencode({'Authorization': key, 'format': 'JSON'})}"


def fetch_typhoons(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[dict]:
    """回傳目前的颱風清單（可能是空的）；連線或格式問題都轉成 UpstreamError。"""
    url = build_url(api_key())
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        # 錯誤訊息只放狀態碼，不放網址：網址裡有金鑰，不能寫進 log
        raise UpstreamError(f"CWA HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise UpstreamTimeout("CWA connect timeout") from exc
        raise UpstreamError(f"CWA connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise UpstreamTimeout("CWA read timeout") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise UpstreamError(f"CWA connection failed: {type(exc).__name__}") from exc

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpstreamError("CWA returned invalid JSON") from exc
    return parse_typhoons(data)


# ---------- 整理成本服務的格式 ----------


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # 排除 NaN


def _coordinate(fix: dict) -> tuple[float, float] | None:
    """氣象署的座標是 "經度,緯度" 字串，例如 "121.5,23.0"。"""
    raw = fix.get("coordinate")
    if not isinstance(raw, str) or "," not in raw:
        return None
    lon, lat = (_number(p) for p in raw.split(",", 1))
    if lon is None or lat is None or not (-90 <= lat <= 90 and -180 <= lon <= 360):
        return None
    return lat, lon


def _radius(fix: dict, key: str) -> float | None:
    value = fix.get(key)
    if isinstance(value, dict):
        value = value.get("radius")
    return _number(value)


def _fixes(section) -> list[dict]:
    fixes = section.get("fix") if isinstance(section, dict) else None
    if isinstance(fixes, dict):  # 只有一筆時可能不是 list
        fixes = [fixes]
    return [f for f in fixes or [] if isinstance(f, dict)]


def _valid_time(init_time, tau_hours: float | None) -> str | None:
    """預報點的時間 = 發布時間 + tau 小時，例如 08:00 發布的 tau=24 是隔天 08:00。"""
    if not isinstance(init_time, str) or tau_hours is None:
        return None
    try:
        return (datetime.fromisoformat(init_time) + timedelta(hours=tau_hours)).isoformat()
    except ValueError:
        return None


def _point(fix: dict, time_key: str) -> dict | None:
    position = _coordinate(fix)
    if position is None:
        return None
    lat, lon = position
    return {
        "time": fix.get(time_key),
        "lat": lat,
        "lon": lon,
        "max_wind_ms": _number(fix.get("maxWindSpeed")),
        "max_gust_ms": _number(fix.get("maxGustSpeed")),
        "pressure_hpa": _number(fix.get("pressure")),
    }


def parse_typhoon(raw: dict) -> dict | None:
    """把一個熱帶氣旋整理成：名稱、過去路徑、目前位置、預測路徑。沒有任何有效座標就回傳 None。"""
    track = [p for f in _fixes(raw.get("analysisData")) if (p := _point(f, "fixTime"))]
    if not track:
        return None
    latest_fix = _fixes(raw.get("analysisData"))[-1]
    current = {
        **track[-1],
        "moving_speed_kmh": _number(latest_fix.get("movingSpeed")),
        "moving_direction": latest_fix.get("movingDirection"),
        "radius_15ms_km": _radius(latest_fix, "circleOf15Ms"),
    }

    forecast = []
    for fix in _fixes(raw.get("forecastData")):
        point = _point(fix, "initTime")
        if point is None:
            continue
        tau = _number(fix.get("tau"))
        point["time"] = _valid_time(point["time"], tau)
        point["tau_hours"] = tau
        point["radius_70pct_km"] = _number(fix.get("radiusOf70PercentProbability"))
        forecast.append(point)

    name_en = raw.get("typhoonName")
    return {
        "name": raw.get("cwaTyphoonName") or name_en or "熱帶性低氣壓",
        "name_en": name_en,
        "number": raw.get("cwaTyNo") or raw.get("cwaTdNo"),
        "current": current,
        "track": [{"time": p["time"], "lat": p["lat"], "lon": p["lon"]} for p in track],
        "forecast": forecast,
    }


def parse_typhoons(data: object) -> list[dict]:
    """沒有颱風時氣象署回傳空清單，這不是錯誤；整體結構不對才是 UpstreamError。"""
    if not isinstance(data, dict) or str(data.get("success")).lower() != "true":
        raise UpstreamError("CWA response is not successful")
    records = data.get("records")
    if not isinstance(records, dict):
        raise UpstreamError("CWA response has no records")
    cyclones = (records.get("tropicalCyclones") or {}).get("tropicalCyclone") or []
    if isinstance(cyclones, dict):
        cyclones = [cyclones]
    if not isinstance(cyclones, list):
        raise UpstreamError("CWA tropicalCyclone is not a list")
    return [t for c in cyclones if isinstance(c, dict) and (t := parse_typhoon(c))]
