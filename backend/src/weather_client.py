"""Open-Meteo Forecast API 客戶端。

只負責「送出 HTTP 請求、檢查回應格式」，不處理城市查找或 HTTP 狀態碼。
只用標準函式庫 urllib，Lambda 打包時不需要第三方套件。
"""

import http.client
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

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

# urllib 的 timeout 只限制「建立連線」和「每一次讀取」，不是整個請求的總時間：
# 上游每次只送一點資料，就可以拖過任何上限。所以整個請求另外用 call_with_deadline 限制總時間。
# 3 秒對 Open-Meteo 很寬裕，又遠小於 Lambda 的執行上限，逾時時還來得及回傳舊資料。
DEFAULT_TIMEOUT_SECONDS = 3.0

# 正常回應不到 1 KB；上限留很大的空間，只擋異常的回應
MAX_RESPONSE_BYTES = 64 * 1024

# 上游失敗後，這段時間內不再呼叫它（有舊資料就直接回舊資料），
# 避免上游故障時每個請求都等一次逾時、佔住 Lambda
BACKOFF_SECONDS = 30

# 在背景執行緒做 HTTP 請求，主執行緒最多等到總時限。
# Lambda 一個執行環境同一時間只處理一個請求；2 個 worker 讓卡住的上一次請求不會擋住下一次。
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="upstream")


class UpstreamError(Exception):
    """Open-Meteo 連線失敗、回傳 HTTP 錯誤，或回傳的資料無法使用。"""


class UpstreamTimeout(UpstreamError):
    """Open-Meteo 在逾時時間內沒有回應。"""


def call_with_deadline(fn: Callable[[], Any], deadline: float, what: str) -> Any:
    """執行 fn，超過 deadline 秒就丟 UpstreamTimeout；fn 自己丟的例外照原樣往上丟。"""
    future = _EXECUTOR.submit(fn)
    try:
        return future.result(timeout=deadline)
    except TimeoutError as exc:
        # 還沒開始執行的就取消；已經在執行的會在 socket 逾時後自己結束
        future.cancel()
        raise UpstreamTimeout(f"{what} deadline exceeded") from exc


class UpstreamBackoff:
    """上游失敗一次後，BACKOFF_SECONDS 秒內直接當作失敗，不再呼叫。"""

    def __init__(
        self,
        seconds: float = BACKOFF_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.seconds = seconds
        self.monotonic = monotonic
        self._skip_until = 0.0

    def call(self, fn: Callable[..., Any], *args) -> Any:
        if self.monotonic() < self._skip_until:
            raise UpstreamError("skipped: upstream failed recently")
        try:
            return fn(*args)
        except UpstreamError:
            self._skip_until = self.monotonic() + self.seconds
            raise

    def reset(self) -> None:
        self._skip_until = 0.0


def _reject_constant(name: str):
    # json 預設會把 NaN、Infinity 解析成 float，但它們不是合法的 JSON，瀏覽器也解析不了
    raise ValueError(f"non-finite number {name}")


def _is_number(value) -> bool:
    # bool 是 int 的子類別，要另外排除；NaN、inf（例如 1e999）也不算
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def build_url(city: City) -> str:
    params = {
        "latitude": city.lat,
        "longitude": city.lon,
        "current": ",".join(CURRENT_FIELDS),
        "timezone": "Asia/Taipei",
    }
    return f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"


def fetch_current(
    city: City,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    deadline: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """回傳 Open-Meteo 的 `current` 區塊；任何問題都轉成 UpstreamError。

    timeout 是每次連線或讀取的上限，deadline 是整個請求的總時間上限。
    """
    url = build_url(city)
    body = call_with_deadline(lambda: _download(url, timeout), deadline, "open-meteo")
    if len(body) > MAX_RESPONSE_BYTES:
        raise UpstreamError("response is too large")

    try:
        data = json.loads(body, parse_constant=_reject_constant)
    except ValueError as exc:
        # JSONDecodeError、UnicodeDecodeError 和 NaN/Infinity 都是 ValueError
        raise UpstreamError("invalid JSON") from exc

    return parse_current(data)


def _download(url: str, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # HTTPError 是 URLError 的子類別，所以要先接
        raise UpstreamError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise UpstreamTimeout("connect timeout") from exc
        raise UpstreamError(f"connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise UpstreamTimeout("read timeout") from exc
    except (OSError, http.client.HTTPException) as exc:
        # urllib 只把「送出請求」時的錯誤包成 URLError；
        # 讀取回應時對方斷線或內容不完整，會直接丟出這兩類例外
        raise UpstreamError(f"connection failed: {exc!r}") from exc


def parse_current(data: object) -> dict:
    """確認 `current` 區塊存在且每個欄位都是有限的數值，否則視為無效資料。"""
    current = data.get("current") if isinstance(data, dict) else None
    if not isinstance(current, dict):
        raise UpstreamError("missing 'current'")

    missing = [f for f in CURRENT_FIELDS if not _is_number(current.get(f))]
    if missing or not isinstance(current.get("time"), str):
        raise UpstreamError(f"missing or invalid fields: {missing or ['time']}")
    return current
