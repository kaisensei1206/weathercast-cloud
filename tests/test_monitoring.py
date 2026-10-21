"""確認告警設定（terraform/main/monitoring.tf）和程式碼、文件一致。

metric filter 是比對 log 的 message 欄位。程式改了 log 名稱，filter 就再也比對不到，
告警會一直維持「正常」而沒人發現；這裡在測試階段就把這種落差抓出來。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "terraform" / "main"
MONITORING = (MAIN / "monitoring.tf").read_text(encoding="utf-8")
APIGATEWAY = (MAIN / "apigateway.tf").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "monitoring.md").read_text(encoding="utf-8")
SRC = ROOT / "backend" / "src"


def logged_messages() -> set[str]:
    text = "\n".join(p.read_text(encoding="utf-8") for p in SRC.glob("*.py"))
    return set(re.findall(r'log\(\s*"\w+",\s*"(\w+)"', text))


def test_metric_filters_match_messages_the_code_logs():
    filtered = set(re.findall(r'\$\.message = \\"(\w+)\\"', MONITORING))
    assert filtered == {
        "upstream_timeout",
        "upstream_error",
        "serving_stale_cache",
        "dynamodb_error",
        "weather_ok",
        "fireworks_ok",
    }
    assert filtered <= logged_messages()


def test_cache_source_values_match_the_code():
    sources = set(re.findall(r'\$\.source = \\"(\w+)\\"', MONITORING))
    code = (SRC / "weather_service.py").read_text(encoding="utf-8")
    code += (SRC / "fireworks_service.py").read_text(encoding="utf-8")
    assert sources == {"cache", "upstream"}
    for source in sources:
        assert f'"{source}"' in code


def test_every_alarm_notifies_on_alarm_and_recovery():
    block = r'resource "aws_cloudwatch_metric_alarm" "alarms" \{(.*?)^\}'
    body = re.search(block, MONITORING, re.M | re.S).group(1)
    assert "alarm_actions       = local.alarm_actions" in body
    assert "ok_actions          = local.alarm_actions" in body
    assert 'treat_missing_data  = "notBreaching"' in body


def test_alarm_count_stays_in_free_tier():
    alarms = re.findall(r"^    ([\w-]+) = \{", MONITORING.split("alarms = {", 1)[1], re.M)
    assert len(alarms) == 7
    assert len(alarms) <= 10  # CloudWatch 每月 10 個標準告警免費


def test_alarms_in_doc_match_terraform():
    alarms = set(re.findall(r"^    ([\w-]+) = \{", MONITORING.split("alarms = {", 1)[1], re.M))
    in_doc = set(re.findall(r"^\| `weathercast-([\w-]+)` \|", DOC, re.M))
    assert in_doc == alarms


def test_email_is_not_in_terraform():
    # email 會進到 state；訂閱改用 AWS CLI 建立
    tf = "\n".join(p.read_text(encoding="utf-8") for p in MAIN.glob("*.tf"))
    assert "aws_sns_topic_subscription" not in tf
    assert "@" not in tf.replace("$context", "")


def test_fireworks_route_has_its_own_lower_throttle():
    settings = re.search(r"^  route_settings \{(.*?)\}", APIGATEWAY, re.M | re.S).group(1)
    assert 'route_key              = "GET /api/fireworks"' in settings
    assert "depends_on = [aws_apigatewayv2_route.routes]" in APIGATEWAY
