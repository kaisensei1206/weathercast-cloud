"""測試共用的 fixture。

所有測試都不連網路：
- `block_network` 自動套用在每個測試上，任何真的對外連線都會讓測試失敗。
- 需要 Open-Meteo 回應的測試使用 `upstream`，它把 urllib 的 urlopen 換成假的，
  由測試決定回傳什麼資料或丟出什麼例外。
"""

import json
import socket
from dataclasses import dataclass

import pytest

import handler
import weather_client
from fakes import FakeUpstream


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("單元測試不可以連到外部網路")

    # 連線前會先查 DNS，兩個都擋才不會漏掉
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def upstream(monkeypatch) -> FakeUpstream:
    fake = FakeUpstream()
    monkeypatch.setattr(weather_client.urllib.request, "urlopen", fake)
    return fake


@dataclass
class Response:
    status: int
    headers: dict
    body: dict

    def assert_error(self, status: int, code: str) -> None:
        """所有錯誤回應都必須是同一種格式：{"error": 代碼, "message": 說明}。"""
        assert self.status == status
        assert self.headers["Content-Type"] == "application/json; charset=utf-8"
        assert self.body["error"] == code
        assert isinstance(self.body["message"], str) and self.body["message"]
        assert set(self.body) <= {"error", "message", "request_id"}


@pytest.fixture
def api():
    """用 API Gateway HTTP API（payload 2.0）格式的事件呼叫 lambda_handler。"""

    def call(path, params=None, method="GET", context=None) -> Response:
        event = {
            "version": "2.0",
            "rawPath": path,
            "queryStringParameters": params,
            "requestContext": {"http": {"method": method, "path": path}},
        }
        result = handler.lambda_handler(event, context)
        return Response(result["statusCode"], result["headers"], json.loads(result["body"]))

    return call
