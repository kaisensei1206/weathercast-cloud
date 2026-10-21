"""Lambda 進入點：API Gateway HTTP API（payload format 2.0）。

這一層只處理 HTTP：解析事件、路由、把業務邏輯的結果與例外轉成狀態碼。
任何沒預期到的例外都在最外層攔下，只回傳 request_id，細節寫進 CloudWatch Logs。

路由（/api 前綴可有可無，之後 CloudFront 會用 /api/* 轉發）：
  GET /health
  GET /cities
  GET /weather?city=Tainan
  GET /fireworks
"""

import json
import os
import traceback

from cities import CITIES
from fireworks_service import get_fireworks
from logger import log
from weather_cache import cache_from_env
from weather_client import UpstreamError, UpstreamTimeout
from weather_service import CityNotFound, InvalidCity, MissingCity, get_weather

# 在模組載入（Lambda 冷啟動）時建立一次，之後同一個執行環境的請求都重複使用同一個連線。
# 環境變數設定錯誤會在這裡丟出例外，冷啟動就失敗，CloudWatch 上看得到。
CACHE = cache_from_env(os.environ)


def respond(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def error(status: int, code: str, message: str, **extra) -> dict:
    return respond(status, {"error": code, "message": message, **extra})


def route(event: dict) -> dict:
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = event.get("rawPath") or http.get("path") or "/"
    if path.startswith("/api/"):
        path = path[len("/api") :]

    if method != "GET":
        return error(405, "method_not_allowed", "只支援 GET")
    if path == "/health":
        return respond(200, {"status": "ok"})
    if path == "/cities":
        return respond(
            200,
            {"cities": [{"id": c.id, "name": c.name_zh, "name_en": c.name_en} for c in CITIES]},
        )
    if path == "/weather":
        return weather((event.get("queryStringParameters") or {}).get("city"))
    if path == "/fireworks":
        return fireworks()
    return error(404, "not_found", "找不到這個路徑")


def weather(query: str | None) -> dict:
    try:
        result = get_weather(query, cache=CACHE)
    except MissingCity:
        return error(400, "missing_city", "請提供 city 參數，例如 ?city=Tainan")
    except InvalidCity:
        return error(400, "invalid_city", "city 參數過長")
    except CityNotFound as exc:
        return error(404, "city_not_found", f"找不到城市：{exc.query}")
    except UpstreamTimeout as exc:
        log("warning", "upstream_timeout", city=query, detail=str(exc))
        return error(504, "upstream_timeout", "氣象資料來源回應逾時，請稍後再試")
    except UpstreamError as exc:
        log("warning", "upstream_error", city=query, detail=str(exc))
        return error(502, "upstream_error", "氣象資料來源暫時無法使用，請稍後再試")

    meta = result["meta"]
    log("info", "weather_ok", city=result["city"]["id"], source=meta["source"], stale=meta["stale"])
    return respond(200, result)


def fireworks() -> dict:
    try:
        result = get_fireworks(cache=CACHE)
    except UpstreamTimeout as exc:
        log("warning", "upstream_timeout", provider="taiwan-tourism", detail=str(exc))
        return error(504, "upstream_timeout", "活動資料來源回應逾時，請稍後再試")
    except UpstreamError as exc:
        log("warning", "upstream_error", provider="taiwan-tourism", detail=str(exc))
        return error(502, "upstream_error", "活動資料來源暫時無法使用，請稍後再試")

    meta = result["meta"]
    log("info", "fireworks_ok", count=len(result["events"]), source=meta["source"])
    return respond(200, result)


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", "local")
    try:
        return route(event)
    except Exception as exc:  # noqa: BLE001 - 最外層保護，避免 traceback 外洩
        log(
            "error",
            "unhandled_exception",
            request_id=request_id,
            error=repr(exc),
            traceback=traceback.format_exc(),
        )
        return error(500, "internal_error", "伺服器發生錯誤", request_id=request_id)
