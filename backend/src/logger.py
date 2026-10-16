"""結構化 log：一行一個 JSON，CloudWatch Logs Insights 可以直接用欄位查詢。

handler 和 weather_service 都會用到，所以獨立成一個模組，避免互相 import。
"""

import json


def log(level: str, message: str, **fields) -> None:
    print(json.dumps({"level": level, "message": message, **fields}, ensure_ascii=False))
