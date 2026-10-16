"""在本機直接呼叫 Lambda handler，不需要部署到 AWS。

組一個 API Gateway HTTP API（payload 2.0）格式的事件，交給 lambda_handler，
再印出狀態碼與回應。/weather 會真的呼叫 Open-Meteo，需要網路。

用法：
  python scripts/invoke_local.py /api/health
  python scripts/invoke_local.py /api/weather city=Tainan
  python scripts/invoke_local.py /api/weather city=台南
  python scripts/invoke_local.py /api/weather            # 缺少 city → 400
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from handler import lambda_handler  # noqa: E402


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/api/health"
    params = dict(arg.split("=", 1) for arg in sys.argv[2:])
    event = {
        "version": "2.0",
        "rawPath": path,
        "queryStringParameters": params or None,
        "requestContext": {"http": {"method": "GET", "path": path}},
    }
    result = lambda_handler(event, None)
    print(result["statusCode"])
    print(json.dumps(json.loads(result["body"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
