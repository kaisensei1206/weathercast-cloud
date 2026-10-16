"""Open-Meteo Forecast API 客戶端。

只負責「送出 HTTP 請求、檢查回應格式」，不處理城市查找或 HTTP 狀態碼。
只用標準函式庫 urllib，Lambda 打包時不需要第三方套件。
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from cities import City

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
)

# urllib 的 timeout 同時套用在「建立連線」和「每一次讀取」上。
# 3 秒對 Open-Meteo 很寬裕，又遠小於 Lambda 的執行上限，逾時時還來得及回應使用者。
DEFAULT_TIMEOUT_SECONDS = 3.0


class UpstreamError(Exception):
    """Open-Meteo 連線失敗、回傳 HTTP 錯誤，或回傳的資料無法使用。"""


class UpstreamTimeout(UpstreamError):
    """Open-Meteo 在逾時時間內沒有回應。"""


def build_url(city: City) -> str:
    params = {
        "latitude": city.lat,
        "longitude": city.lon,
        "current": ",".join(CURRENT_FIELDS),
        "timezone": "Asia/Taipei",
    }
    return f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"


def fetch_current(city: City, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """回傳 Open-Meteo 的 `current` 區塊；任何問題都轉成 UpstreamError。"""
    try:
        with urllib.request.urlopen(build_url(city), timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        # HTTPError 是 URLError 的子類別，所以要先接
        raise UpstreamError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise UpstreamTimeout("connect timeout") from exc
        raise UpstreamError(f"connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise UpstreamTimeout("read timeout") from exc

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpstreamError("invalid JSON") from exc

    return parse_current(data)


def parse_current(data: object) -> dict:
    """確認 `current` 區塊存在且每個欄位都是數值，否則視為無效資料。"""
    current = data.get("current") if isinstance(data, dict) else None
    if not isinstance(current, dict):
        raise UpstreamError("missing 'current'")

    missing = [f for f in CURRENT_FIELDS if not isinstance(current.get(f), int | float)]
    if missing or not isinstance(current.get("time"), str):
        raise UpstreamError(f"missing or invalid fields: {missing or ['time']}")
    return current
