"""部署後的冒煙測試：確認線上 API 真的能回應。

打 /api/health 和 /api/weather?city=Tainan，檢查狀態碼和回應內容。
加上 --frontend 時，再檢查首頁是 WeatherCast 的 HTML；用來測 CloudFront 網址，
同時確認 CloudFront 有把 /api/* 轉給 API Gateway。
Lambda 更新後的前幾秒可能還是舊版本或正在切換，所以失敗會重試幾次。

用法：
  python scripts/smoke_test.py https://<api-id>.execute-api.ap-northeast-1.amazonaws.com
  python scripts/smoke_test.py https://<id>.cloudfront.net --frontend
"""

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable

ATTEMPTS = 5
DELAY_SECONDS = 3


def get_text(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def get_json(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def check_health(base: str, fetch) -> str | None:
    status, body = fetch(f"{base}/api/health")
    if status != 200 or body != {"status": "ok"}:
        return f"/api/health returned {status} {body}"
    return None


def check_weather(base: str, fetch) -> str | None:
    status, body = fetch(f"{base}/api/weather?city=Tainan")
    if status != 200 or body.get("city", {}).get("id") != "tainan":
        return f"/api/weather?city=Tainan returned {status} {body}"
    if "temperature" not in body.get("current", {}):
        return f"/api/weather?city=Tainan has no temperature: {body}"
    return None


def check_homepage(base: str, fetch_text) -> str | None:
    status, html = fetch_text(f"{base}/")
    if status != 200 or '<div id="root">' not in html or "WeatherCast" not in html:
        return f"/ returned {status}, not the WeatherCast page"
    return None


def run(
    base: str,
    fetch: Callable[[str], tuple[int, dict]] = get_json,
    sleep: Callable[[float], None] = time.sleep,
    *,
    frontend: bool = False,
    fetch_text: Callable[[str], tuple[int, str]] = get_text,
) -> list[str]:
    """回傳失敗訊息；空清單代表通過。"""
    base = base.rstrip("/")
    errors: list[str] = []
    for attempt in range(1, ATTEMPTS + 1):
        try:
            checks = [check_health(base, fetch), check_weather(base, fetch)]
            if frontend:
                checks.append(check_homepage(base, fetch_text))
            errors = [e for e in checks if e]
        except (OSError, ValueError) as exc:  # 連線失敗、逾時、回應不是 JSON
            errors = [f"request failed: {exc!r}"]
        if not errors:
            return []
        print(f"attempt {attempt}/{ATTEMPTS} failed: {errors}")
        if attempt < ATTEMPTS:
            sleep(DELAY_SECONDS)
    return errors


def main(argv: list[str]) -> int:
    frontend = "--frontend" in argv[2:]
    errors = run(argv[1], frontend=frontend)
    if errors:
        print("Smoke test FAILED:", *errors, sep="\n  ")
        return 1
    pages = "/, /api/health" if frontend else "/api/health"
    print(f"Smoke test passed: {pages} and /api/weather?city=Tainan returned 200.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
