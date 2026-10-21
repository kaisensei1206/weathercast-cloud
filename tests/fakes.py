"""測試用的假資料與假物件，給 conftest.py 和各測試檔共用。"""

import io
import json
import zipfile

# moto 模擬的 DynamoDB 資料表名稱
TABLE_NAME = "weathercast-cache-test"

# Open-Meteo `current` 區塊的範例，欄位和真實回應相同
SAMPLE_CURRENT = {
    "time": "2026-10-16T19:45",
    "interval": 900,
    "temperature_2m": 27.7,
    "apparent_temperature": 31.9,
    "relative_humidity_2m": 76,
    "precipitation": 0.0,
    "wind_speed_10m": 8.7,
    "weather_code": 1,
}


# 觀光署 EventList.json 的一筆活動，欄位和 2026-10-21 下載的真實資料相同（說明文字縮短）
SAMPLE_EVENT = {
    "EventID": "Event_376540000A_006236",
    "EventName": "2026成功鎮花火之夜",
    "Description": "除夕夜，海風輕拂，煙花在夜空中璀璨綻放。",
    "PositionLat": 23.10404,
    "PositionLon": 121.38497,
    "PostalAddress": {"City": "臺東縣", "Town": "成功鎮", "StreetAddress": "海濱公園"},
    "Images": [
        {"Name": "2026成功鎮花火之夜", "URL": "https://tour.taitung.gov.tw/image/54819/640x480"}
    ],
    "Organizations": [],
    "WebsiteURL": "",
    "StartDateTime": "2026-02-16T21:00:00+08:00",
    "EndDateTime": "2026-02-16T23:59:59+08:00",
    "EventStatus": "EventScheduled",
}


def event_list(*events: dict) -> dict:
    return {"UpdateTime": "2026-10-21T14:30:00+08:00", "Language": "zh-tw", "Events": list(events)}


def tourism_zip(data, name: str = "EventList.json") -> bytes:
    """組出和觀光署相同結構的 zip；JSON 前面加 BOM，和真實檔案一樣。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        content = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        archive.writestr(name, b"\xef\xbb\xbf" + content)
        archive.writestr("manifest.csv", "file,count\n")
    return buffer.getvalue()


class FakeUpstream:
    """假的 urlopen：記錄每次呼叫，回傳設定好的內容或丟出設定好的例外。"""

    def __init__(self):
        self.calls: list[dict] = []
        self.body = json.dumps({"current": SAMPLE_CURRENT}).encode()
        self.exc: BaseException | None = None

    def returns(self, payload) -> None:
        """設定回應內容；dict/list 會轉成 JSON，bytes 原樣回傳。"""
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.exc = None

    def raises(self, exc: BaseException) -> None:
        self.exc = exc

    def __call__(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        if self.exc is not None:
            raise self.exc
        return io.BytesIO(self.body)
