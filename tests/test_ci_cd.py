"""CI/CD：部署前的 plan 檢查、部署後的冒煙測試，以及 workflow 與部署角色的安全設定。

workflow 和 IAM policy 寫錯不會讓程式壞掉，卻可能讓 PR 也能部署、或讓部署角色拿到太大的權限。
這些設定很少改，改的時候也不容易被發現，所以用測試鎖住。
"""

import json
import re
import urllib.error
from pathlib import Path

import pytest
import yaml

import check_plan
import smoke_test

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-cd.yml").read_text("utf-8"))
OIDC_TF = (ROOT / "terraform" / "bootstrap" / "github_oidc.tf").read_text("utf-8")
FRONTEND_TF = (ROOT / "terraform" / "main" / "frontend.tf").read_text("utf-8")


# --- check_plan：只允許更新 Lambda ---------------------------------------------


def change(address: str, *actions: str, mode: str = "managed") -> dict:
    return {"address": address, "mode": mode, "change": {"actions": list(actions)}}


def plan_file(tmp_path, *changes) -> str:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"resource_changes": list(changes)}), encoding="utf-8")
    return str(path)


def test_no_changes_is_allowed(tmp_path, capsys):
    path = plan_file(tmp_path, change("aws_dynamodb_table.cache", "no-op"))
    assert check_plan.main(["check_plan.py", path]) == 0
    assert "No changes." in capsys.readouterr().out


def test_lambda_update_is_allowed(tmp_path, capsys):
    path = plan_file(
        tmp_path,
        change("aws_lambda_function.api", "update"),
        change("aws_dynamodb_table.cache", "no-op"),
        change("data.aws_iam_policy_document.lambda", "read", mode="data"),
    )
    assert check_plan.main(["check_plan.py", path]) == 0
    assert "[ok] update" in capsys.readouterr().out


@pytest.mark.parametrize(
    "blocked",
    [
        pytest.param(change("aws_dynamodb_table.extra", "create"), id="new-resource"),
        pytest.param(change("aws_iam_role_policy.lambda", "update"), id="iam-change"),
        pytest.param(change("aws_dynamodb_table.cache", "delete"), id="delete"),
        pytest.param(change("aws_lambda_function.api", "delete", "create"), id="lambda-replace"),
    ],
)
def test_infrastructure_changes_are_blocked(tmp_path, capsys, blocked):
    path = plan_file(tmp_path, change("aws_lambda_function.api", "update"), blocked)
    assert check_plan.main(["check_plan.py", path]) == 1
    out = capsys.readouterr().out
    assert f"[BLOCKED] {','.join(blocked['change']['actions'])}" in out
    assert "apply it locally" in out


# --- smoke_test：部署後確認線上 API ----------------------------------------------

BASE = "https://example.execute-api.ap-northeast-1.amazonaws.com"
HEALTHY = {
    f"{BASE}/api/health": (200, {"status": "ok"}),
    f"{BASE}/api/weather?city=Tainan": (
        200,
        {"city": {"id": "tainan"}, "current": {"temperature": 27}},
    ),
}


class FakeFetch:
    def __init__(self, *rounds: dict):
        self.rounds = list(rounds)
        self.urls: list[str] = []

    def __call__(self, url: str):
        self.urls.append(url)
        responses = self.rounds[0] if len(self.rounds) == 1 else self.rounds.pop(0)
        result = responses[url]
        if isinstance(result, Exception):
            raise result
        return result


def test_smoke_test_passes(capsys):
    fetch, sleeps = FakeFetch(HEALTHY), []
    assert smoke_test.run(BASE + "/", fetch, sleeps.append) == []
    assert fetch.urls == list(HEALTHY)  # 結尾的 / 不會變成 //
    assert sleeps == []


def test_smoke_test_retries_until_lambda_is_ready():
    not_ready = {url: (502, {}) for url in HEALTHY}
    sleeps = []
    assert smoke_test.run(BASE, FakeFetch(not_ready, HEALTHY), sleeps.append) == []
    assert sleeps == [smoke_test.DELAY_SECONDS]


@pytest.mark.parametrize(
    ("url", "response", "message"),
    [
        (f"{BASE}/api/health", (500, {}), "/api/health returned 500"),
        (f"{BASE}/api/weather?city=Tainan", (200, {"city": {"id": "taipei"}}), "returned 200"),
        (f"{BASE}/api/weather?city=Tainan", (200, {"city": {"id": "tainan"}}), "no temperature"),
        (f"{BASE}/api/health", TimeoutError("timed out"), "request failed"),
        (f"{BASE}/api/health", ValueError("not json"), "request failed"),
    ],
)
def test_smoke_test_fails_after_all_attempts(url, response, message):
    broken = {**HEALTHY, url: response}
    sleeps = []
    errors = smoke_test.run(BASE, FakeFetch(broken), sleeps.append)
    assert errors and message in errors[0]
    assert len(sleeps) == smoke_test.ATTEMPTS - 1


def test_smoke_test_main_exit_codes(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(smoke_test, "run", lambda base, frontend: calls.append(frontend) or [])
    assert smoke_test.main(["smoke_test.py", BASE]) == 0
    assert smoke_test.main(["smoke_test.py", BASE, "--frontend"]) == 0
    assert calls == [False, True]
    assert "Smoke test passed: /, /api/health" in capsys.readouterr().out
    monkeypatch.setattr(smoke_test, "run", lambda base, frontend: ["/api/health returned 500 {}"])
    assert smoke_test.main(["smoke_test.py", BASE]) == 1
    assert "FAILED" in capsys.readouterr().out


HOMEPAGE = '<html><title>WeatherCast</title><div id="root"></div></html>'


def test_smoke_test_checks_homepage_only_for_frontend():
    pages = []

    def fetch_text(url):
        pages.append(url)
        return 200, HOMEPAGE

    assert smoke_test.run(BASE, FakeFetch(HEALTHY), [].append, fetch_text=fetch_text) == []
    assert pages == []
    assert (
        smoke_test.run(BASE, FakeFetch(HEALTHY), [].append, frontend=True, fetch_text=fetch_text)
        == []
    )
    assert pages == [f"{BASE}/"]


@pytest.mark.parametrize(
    "page",
    [
        (403, ""),  # bucket policy 或 OAC 設錯
        (200, "<html>Some other site</html>"),
        (200, '{"message": "Not Found"}'),  # 首頁被轉到 API Gateway
    ],
)
def test_smoke_test_fails_on_wrong_homepage(page):
    errors = smoke_test.run(
        BASE, FakeFetch(HEALTHY), [].append, frontend=True, fetch_text=lambda url: page
    )
    assert errors == [f"/ returned {page[0]}, not the WeatherCast page"]


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b'{"status": "ok"}'


def test_get_json_reads_status_and_body(monkeypatch):
    monkeypatch.setattr(smoke_test.urllib.request, "urlopen", lambda url, timeout: FakeResponse())
    assert smoke_test.get_json(BASE) == (200, {"status": "ok"})


def test_get_text_reads_status_and_body(monkeypatch):
    monkeypatch.setattr(smoke_test.urllib.request, "urlopen", lambda url, timeout: FakeResponse())
    assert smoke_test.get_text(BASE) == (200, '{"status": "ok"}')


def test_get_text_returns_http_error_status(monkeypatch):
    def raise_403(url, timeout):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(smoke_test.urllib.request, "urlopen", raise_403)
    assert smoke_test.get_text(BASE) == (403, "")


def test_get_json_returns_http_error_status(monkeypatch):
    def raise_404(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(smoke_test.urllib.request, "urlopen", raise_404)
    assert smoke_test.get_json(BASE) == (404, {})


# --- workflow：PR 不能部署，CI 沒過不能部署 ------------------------------------


def test_workflow_has_no_default_permissions():
    assert WORKFLOW["permissions"] == {}


def test_deploy_requires_tests_and_never_runs_on_pull_requests():
    deploy = WORKFLOW["jobs"]["deploy"]
    assert deploy["needs"] == ["test", "frontend"]
    assert "github.event_name != 'pull_request'" in deploy["if"]
    assert "github.ref == 'refs/heads/main'" in deploy["if"]


def test_only_deploy_job_can_request_aws_credentials():
    jobs = WORKFLOW["jobs"]
    assert jobs["deploy"]["permissions"]["id-token"] == "write"
    others = [name for name in jobs if name != "deploy"]
    assert others == ["test", "frontend"]
    for name in others:
        assert "id-token" not in jobs[name]["permissions"]


def test_workflow_uses_no_long_lived_aws_keys():
    text = (ROOT / ".github" / "workflows" / "ci-cd.yml").read_text("utf-8")
    assert "secrets." not in text
    assert "aws-access-key-id" not in text
    assert "vars.AWS_DEPLOY_ROLE_ARN" in text


def test_workflow_region_matches_terraform():
    variables = (ROOT / "terraform" / "main" / "variables.tf").read_text("utf-8")
    default = re.search(r'variable "region".*?default\s*=\s*"([^"]+)"', variables, re.DOTALL)
    assert WORKFLOW["env"]["AWS_REGION"] == default.group(1)


# --- 部署角色：只信任 main，不能建立資源或改 IAM ---------------------------------


def test_deploy_role_trusts_only_main_branch_of_this_repo():
    assert '"${local.github_subject_prefix}:ref:refs/heads/main"' in OIDC_TF
    prefix = 'github_subject_prefix = "repo:${local.github_owner}@${var.github_owner_id}/'
    assert prefix + '${local.github_repo_name}@${var.github_repository_id}"' in OIDC_TF
    assert '"sts.amazonaws.com"' in OIDC_TF


def test_deploy_role_cannot_create_delete_or_escalate():
    # 只看 actions = [...]；condition 裡的 "s3:prefix" 之類是條件鍵，不是權限
    lists = re.findall(r"^\s*actions\s*=\s*\[(.*?)\]", OIDC_TF, re.MULTILINE)
    actions = set(re.findall(r'"([^"]+)"', ",".join(lists))) - {"sts:AssumeRoleWithWebIdentity"}
    writes = {a for a in actions if not re.search(r":(Get|List|Describe)|apigateway:GET", a)}
    assert writes == {
        "s3:PutObject",
        "s3:DeleteObject",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "cloudfront:CreateInvalidation",
    }
    assert not any(a.endswith(":*") for a in actions)
    assert "iam:PassRole" not in actions


def test_deploy_role_writes_only_to_frontend_bucket_and_state():
    # S3 的寫入只能落在 state 的 key 或前端 bucket，不能寫到帳號裡其他 bucket
    statements = re.findall(r"statement \{(.*?)\n  \}", OIDC_TF, re.DOTALL)
    assert sum('"s3:PutObject"' in body for body in statements) == 2
    for body in statements:
        if '"s3:PutObject"' in body:
            resources = re.search(r"resources\s*=\s*\[(.*?)\]", body).group(1)
            assert resources in (
                '"${aws_s3_bucket.tf_state.arn}/weathercast/main.tfstate*"',
                '"${local.frontend_bucket_arn}/*"',
            )


def test_frontend_bucket_name_matches_main_stack():
    assert (
        'frontend_bucket = "${var.project_name}-frontend-${data.aws_caller_identity' in FRONTEND_TF
    )
    assert '"arn:aws:s3:::${var.project_name}-frontend-${local.account_id}"' in OIDC_TF


# --- 前端：bucket 不公開，只有這個 CloudFront 能讀 ---------------------------------


def test_frontend_bucket_is_private_and_readable_only_by_this_distribution():
    for flag in [
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ]:
        assert re.search(rf"{flag}\s*=\s*true", FRONTEND_TF)
    assert '"cloudfront.amazonaws.com"' in FRONTEND_TF
    assert 'variable = "AWS:SourceArn"' in FRONTEND_TF
    assert "values   = [aws_cloudfront_distribution.frontend.arn]" in FRONTEND_TF
    assert 'signing_behavior                  = "always"' in FRONTEND_TF
    assert "website" not in FRONTEND_TF.replace(
        "# ", ""
    )  # 不開 S3 static website hosting（只支援 HTTP）


def test_cloudfront_forwards_api_without_caching_or_rewriting_errors():
    api = re.search(r"ordered_cache_behavior \{(.*?)\n  \}", FRONTEND_TF, re.DOTALL).group(1)
    assert 'path_pattern               = "/api/*"' in api
    assert "local.cache_policy_caching_disabled" in api
    assert "local.origin_request_all_except_host" in api  # 轉送 Host 會讓 API Gateway 回 403
    # 錯誤頁改寫會套用到 /api/*，把 404 city_not_found 換成 HTML
    assert "custom_error_response {" not in FRONTEND_TF
    assert FRONTEND_TF.count('viewer_protocol_policy     = "redirect-to-https"') == 2


def test_deploy_uploads_assets_before_index_and_uses_relative_api():
    steps = WORKFLOW["jobs"]["deploy"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Terraform apply") < names.index("Upload frontend to S3")
    assert names.index("Upload frontend to S3") < names.index("Invalidate CloudFront cache")
    upload = steps[names.index("Upload frontend to S3")]["run"].splitlines()
    assert "dist/assets" in upload[0] and "immutable" in upload[0]
    assert '--exclude "assets/*"' in upload[1] and "no-cache" in upload[1]
    text = (ROOT / ".github" / "workflows" / "ci-cd.yml").read_text("utf-8")
    assert "VITE_API_BASE_URL=" not in text and "VITE_API_BASE_URL:" not in text
    assert "--frontend" in steps[names.index("Smoke test")]["run"]


# --- 供應鏈：有 AWS 憑證的 job 只執行釘選過的程式碼 -----------------------------


def test_every_action_is_pinned_to_a_commit_sha():
    # tag（例如 @v5）可以被改指到別的 commit；SHA 不行。版本號寫在後面的註解
    uses = [s["uses"] for job in WORKFLOW["jobs"].values() for s in job["steps"] if "uses" in s]
    assert uses
    unpinned = [u for u in uses if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u)]
    assert unpinned == []


def test_job_with_aws_credentials_does_not_run_npm():
    # npm 套件（含建置工具）的程式碼不能在拿到 AWS 臨時憑證的 job 裡執行
    for name, job in WORKFLOW["jobs"].items():
        if job.get("permissions", {}).get("id-token") == "write":
            steps = json.dumps(job["steps"])
            assert "npm " not in steps, name
            assert "setup-node" not in steps, name


def test_deploy_uses_the_build_from_the_frontend_job():
    frontend = WORKFLOW["jobs"]["frontend"]
    assert "id-token" not in frontend["permissions"]
    upload = [s for s in frontend["steps"] if "upload-artifact" in s.get("uses", "")]
    assert len(upload) == 1 and upload[0]["with"]["name"] == "frontend-dist"

    deploy = WORKFLOW["jobs"]["deploy"]["steps"]
    names = [s.get("name") for s in deploy]
    download = deploy[names.index("Download frontend build")]
    assert "download-artifact" in download["uses"]
    assert download["with"]["name"] == "frontend-dist"
    assert names.index("Download frontend build") < names.index("Upload frontend to S3")
