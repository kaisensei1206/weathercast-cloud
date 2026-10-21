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

# 氣象署 W-C0034-005（颱風路徑）回應的範例。
# 欄位依氣象署開放資料文件整理，還沒有用真實回應核對過，見 docs/typhoon.md
SAMPLE_CWA = {
    "success": "true",
    "records": {
        "tropicalCyclones": {
            "tropicalCyclone": [
                {
                    "year": "2026",
                    "typhoonName": "FUNG-WONG",
                    "cwaTyphoonName": "鳳凰",
                    "cwaTyNo": "26",
                    "analysisData": {
                        "fix": [
                            {
                                "fixTime": "2026-10-20T08:00:00+08:00",
                                "coordinate": "128.0,18.5",
                                "maxWindSpeed": "33",
                                "maxGustSpeed": "43",
                                "pressure": "965",
                                "movingSpeed": "18",
                                "movingDirection": "WNW",
                                "circleOf15Ms": {"radius": "200"},
                            },
                            {
                                "fixTime": "2026-10-20T14:00:00+08:00",
                                "coordinate": "127.0,19.0",
                                "maxWindSpeed": "38",
                                "maxGustSpeed": "48",
                                "pressure": "955",
                                "movingSpeed": "20",
                                "movingDirection": "WNW",
                                "circleOf15Ms": {"radius": "250"},
                            },
                        ]
                    },
                    "forecastData": {
                        "fix": [
                            {
                                "initTime": "2026-10-20T14:00:00+08:00",
                                "tau": "24",
                                "coordinate": "124.5,20.5",
                                "maxWindSpeed": "43",
                                "maxGustSpeed": "53",
                                "pressure": "945",
                                "radiusOf70PercentProbability": "120",
                            },
                            {
                                "initTime": "2026-10-20T14:00:00+08:00",
                                "tau": "48",
                                "coordinate": "122.0,22.5",
                                "maxWindSpeed": "40",
                                "pressure": "950",
                                "radiusOf70PercentProbability": "200",
                            },
                        ]
                    },
                }
            ]
        }
    },
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
