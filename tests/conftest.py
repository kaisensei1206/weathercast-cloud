"""測試共用的 fixture。

所有測試都不連網路：
- `block_network` 自動套用在每個測試上，任何真的對外連線都會讓測試失敗。
- 需要 Open-Meteo 回應的測試使用 `upstream`，它把 urllib 的 urlopen 換成假的，
  由測試決定回傳什麼資料或丟出什麼例外。
- 需要氣象署颱風資料的測試使用 `cwa`，做法相同。
- 需要 DynamoDB 的測試使用 `cache_table`，它用 moto 在記憶體裡模擬 DynamoDB，
  不需要 AWS 帳號，也不會產生費用。
"""

import json
import socket
from dataclasses import dataclass

import boto3
import pytest
from moto import mock_aws

import handler
import typhoon_client
import weather_client
from fakes import SAMPLE_CWA, TABLE_NAME, FakeUpstream


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("單元測試不可以連到外部網路")

    # 連線前會先查 DNS，兩個都擋才不會漏掉
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture(autouse=True)
def isolate_aws(monkeypatch):
    """不讓測試讀到開發者電腦上的 AWS 設定或帳號，也讓 handler 預設不使用快取。"""
    names = ("CACHE_TABLE", "CACHE_FRESH_SECONDS", "CACHE_RETAIN_SECONDS", "AWS_PROFILE")
    for name in (*names, "CWA_API_KEY", "CWA_API_KEY_PARAM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setattr(handler, "CACHE", None)
    typhoon_client.reset_key_cache()


@pytest.fixture
def cache_table():
    """moto 模擬的 DynamoDB 資料表，結構和第六階段 Terraform 會建立的相同。"""
    with mock_aws():
        yield boto3.resource("dynamodb").create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "city_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "city_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


@pytest.fixture
def cwa(monkeypatch) -> FakeUpstream:
    """假的氣象署：金鑰用環境變數提供，urlopen 預設回傳 SAMPLE_CWA。"""
    monkeypatch.setenv("CWA_API_KEY", "test-key")
    fake = FakeUpstream()
    fake.returns(SAMPLE_CWA)
    monkeypatch.setattr(typhoon_client.urllib.request, "urlopen", fake)
    return fake


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
