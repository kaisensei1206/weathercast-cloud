"""交通部觀光署「觀光資訊資料庫－活動」客戶端：下載全臺活動，挑出和煙火有關的活動。

資料是公開的 zip（裡面一個 EventList.json，約 1,000 多筆活動），不需要金鑰，每天更新。
和 weather_client 一樣只用標準函式庫：urllib 下載、zipfile 解壓縮、json 解析。
"""

import http.client
import io
import json
import urllib.error
import urllib.request
import zipfile
from datetime import datetime

from weather_client import UpstreamError, UpstreamTimeout, call_with_deadline

EVENTS_URL = "https://media.taiwan.net.tw/XMLReleaseAll_public/v2.0/Zh_tw/Event-json.zip"
EVENTS_FILE = "EventList.json"

# zip 約 0.5 MB，比 Open-Meteo 的回應大很多，給 5 秒。
# timeout 是每次連線或讀取的上限；整個下載的總時間另外用 call_with_deadline 限制在同樣的 5 秒。
# 最壞情況：讀 DynamoDB 2 秒 + 下載 5 秒 + 寫 DynamoDB 2 秒，仍在 Lambda 的 10 秒逾時內。
DEFAULT_TIMEOUT_SECONDS = 5.0

# 外部檔案不可全信：下載和解壓縮後的大小都設上限，避免異常的大檔或 zip bomb 吃光 Lambda 記憶體。
# 2026-10 實測 zip 約 0.5 MB、EventList.json 約 2.8 MB，上限抓 10 倍以上的空間。
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 50 * 1024 * 1024

KEYWORDS = ("煙火", "烟火", "花火", "焰火")


def fetch_events(
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    deadline: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    """下載活動資料，回傳整理好的煙火相關活動；連線或格式問題都轉成 UpstreamError。"""
    body = call_with_deadline(lambda: _download(timeout), deadline, "tourism")
    if len(body) > MAX_ZIP_BYTES:
        raise UpstreamError("tourism zip is too large")
    return parse_events(read_event_list(body))


def _download(timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(EVENTS_URL, timeout=timeout) as resp:
            return resp.read(MAX_ZIP_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise UpstreamError(f"tourism HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise UpstreamTimeout("tourism connect timeout") from exc
        raise UpstreamError(f"tourism connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise UpstreamTimeout("tourism read timeout") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise UpstreamError(f"tourism connection failed: {exc!r}") from exc


def read_event_list(body: bytes) -> object:
    """從 zip 取出 EventList.json 並解析；檔案有 UTF-8 BOM，用 utf-8-sig 讀。"""
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            info = archive.getinfo(EVENTS_FILE)
            if info.file_size > MAX_JSON_BYTES:
                raise UpstreamError(f"{EVENTS_FILE} is too large")
            raw = archive.read(info)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise UpstreamError(f"tourism zip is invalid: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpstreamError(f"{EVENTS_FILE} is not valid JSON") from exc


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coordinate(value, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if low <= value <= high else None


def _time(value) -> str | None:
    """觀光署的時間是 ISO 8601（含 +08:00）；看不懂的當作沒有。"""
    text = _text(value)
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return None
    return text


def _first(items, key: str) -> str | None:
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and _text(item.get(key)):
                return _text(item.get(key))
    return None


def classify(name: str, description: str) -> str | None:
    """名稱有煙火 → 煙火大會；只有說明提到 → 可能有煙火。

    只有說明提到的，可能是音樂節最後放煙火，也可能只是順帶提到，所以不能直接當成煙火大會。
    """
    if any(k in name for k in KEYWORDS):
        return "fireworks"
    if any(k in description for k in KEYWORDS):
        return "maybe"
    return None


def parse_event(raw: dict) -> dict | None:
    """整理一筆活動；不是煙火相關、已取消，或缺少名稱、時間、座標的都回傳 None。"""
    name = _text(raw.get("EventName"))
    kind = classify(name, _text(raw.get("Description")))
    if kind is None or not name or raw.get("EventStatus") == "EventCancelled":
        return None

    start, end = _time(raw.get("StartDateTime")), _time(raw.get("EndDateTime"))
    lat = _coordinate(raw.get("PositionLat"), -90, 90)
    lon = _coordinate(raw.get("PositionLon"), -180, 180)
    if start is None or lat is None or lon is None:
        return None

    address = raw.get("PostalAddress") if isinstance(raw.get("PostalAddress"), dict) else {}
    return {
        "id": _text(raw.get("EventID")),
        "name": name,
        "kind": kind,
        "start": start,
        "end": end or start,
        "city": _text(address.get("City")),
        "town": _text(address.get("Town")),
        "address": _text(address.get("StreetAddress")),
        "lat": lat,
        "lon": lon,
        "url": _text(raw.get("WebsiteURL")) or None,
        "image": _first(raw.get("Images"), "URL"),
        "organizer": _first(raw.get("Organizations"), "Name"),
    }


def _dedupe_key(event: dict) -> tuple[str, str]:
    # 同一個活動有時會登錄兩次（例如日月潭花火音樂嘉年華），名稱只差空白、開始日期相同
    return "".join(event["name"].split()), event["start"][:10]


def parse_events(data: object) -> list[dict]:
    """回傳煙火相關活動，依開始時間排序；整體結構不對才算錯誤，個別壞掉的活動略過。"""
    events = data.get("Events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        raise UpstreamError(f"{EVENTS_FILE} has no Events list")

    result, seen = [], set()
    for raw in events:
        event = parse_event(raw) if isinstance(raw, dict) else None
        if event is None or _dedupe_key(event) in seen:
            continue
        seen.add(_dedupe_key(event))
        result.append(event)
    return sorted(result, key=lambda e: e["start"])
