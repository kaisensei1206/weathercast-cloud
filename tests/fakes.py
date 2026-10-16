"""測試用的假資料與假物件，給 conftest.py 和各測試檔共用。"""

import io
import json

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
