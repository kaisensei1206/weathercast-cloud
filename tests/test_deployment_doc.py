"""確認部署手冊（docs/deployment.md）和目前的 Terraform、程式碼一致。

手冊裡的指令是給人照著執行的。Terraform 改了資源名稱、output 或路由，手冊卻沒跟著改，
照著做就會在 AWS 上失敗；這裡在測試階段就把這種落差抓出來。
"""

import json
import re
from pathlib import Path

import handler

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
SRC = ROOT / "backend" / "src"

# 只看 PowerShell 程式碼區塊，並去掉 # 之後的註解，避免把說明文字當成指令
POWERSHELL = "\n".join(
    re.sub(r"\s#.*", "", line)
    for block in re.findall(r"```powershell\n(.*?)```", DOC, re.DOTALL)
    for line in block.splitlines()
)

# terraform fmt 保證最外層區塊的結尾 } 在行首，所以可以用正規表示式切出每個區塊
BLOCK = re.compile(
    r'^(resource|variable) "(\w+)"(?: "(\w+)")? \{(.*?)^\}', re.MULTILINE | re.DOTALL
)


def tf_text(stack: str) -> str:
    files = sorted((ROOT / "terraform" / stack).glob("*.tf"))
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


def local_map_keys(text: str, name: str) -> list[str]:
    """locals 裡 `name = { key = ... }` 的第一層 key；terraform fmt 固定用兩格縮排。"""
    body = re.search(rf"^  {name} = \{{\n(.*?)^  \}}", text, re.MULTILINE | re.DOTALL)
    return re.findall(r"^    ([\w-]+)\s+=", body.group(1), re.MULTILINE)


def resource_addresses(stack: str) -> set[str]:
    """terraform plan 會列出的資源位址；for_each 的資源每個 key 各算一個。"""
    text = tf_text(stack)
    addresses = set()
    for kind, rtype, name, body in BLOCK.findall(text):
        if kind != "resource":
            continue
        keys = []
        if for_each := re.search(r"for_each\s*=\s*toset\(\[(.*?)\]\)", body, re.DOTALL):
            keys = re.findall(r'"([^"]+)"', for_each.group(1))
        elif for_each := re.search(r"for_each\s*=\s*local\.(\w+)", body):
            keys = local_map_keys(text, for_each.group(1))
        addresses |= {f'{rtype}.{name}["{k}"]' for k in keys} or {f"{rtype}.{name}"}
    return addresses


def variable_defaults(stack: str) -> dict[str, str]:
    defaults = {}
    for kind, name, _, body in BLOCK.findall(tf_text(stack)):
        match = re.search(r"^\s*default\s*=\s*(.+)$", body, re.MULTILINE)
        if kind == "variable" and match:
            defaults[name] = match.group(1).strip().removeprefix('"').removesuffix('"')
    return defaults


def test_resource_list_in_doc_matches_terraform():
    in_doc = set(re.findall(r"# (.+?) will be created", DOC))
    assert in_doc == resource_addresses("main") | resource_addresses("bootstrap")


def test_plan_counts_in_doc_match_terraform():
    main, bootstrap = len(resource_addresses("main")), len(resource_addresses("bootstrap"))
    assert f"Plan: {main} to add, 0 to change, 0 to destroy." in DOC
    assert f"Plan: {bootstrap} to add, 0 to change, 0 to destroy." in DOC
    assert f"Plan: 0 to add, 0 to change, {main} to destroy." in DOC


def test_terraform_outputs_used_in_doc_exist():
    outputs = tf_text("main") + tf_text("bootstrap")
    declared = set(re.findall(r'^output "(\w+)"', outputs, re.MULTILINE))
    used = set(re.findall(r"output -raw (\w+)", POWERSHELL))
    assert used
    assert used <= declared


def test_aws_resource_names_in_doc_match_terraform():
    project = variable_defaults("main")["project_name"]
    templates = re.findall(
        r'^\s*(?:name|function_name)\s*=\s*"([^"]+)"', tf_text("main"), re.MULTILINE
    )
    created = {
        t.replace("${local.function_name}", "${var.project_name}-api").replace(
            "${var.project_name}", project
        )
        for t in templates
    }

    flags = r"--(?:function-name|table-name|role-name|policy-name) (\S+)"
    used = set(re.findall(flags, POWERSHELL))
    used |= set(re.findall(r"aws logs tail (\S+)", POWERSHELL))
    used |= set(re.findall(r"Name=='([^']+)'", POWERSHELL))
    assert used
    assert used <= created

    for prefix in re.findall(r"--log-group-name-prefix (\S+)", POWERSHELL):
        assert any(name.startswith(prefix) for name in created), prefix


def test_routes_tested_in_doc_exist():
    routes = set(re.findall(r'"GET (/api/\w+)"', tf_text("main")))
    used = set(re.findall(r"\$api(/api/\w+)", POWERSHELL))
    assert used
    assert used <= routes


def test_variable_defaults_in_doc_match_terraform():
    defaults = variable_defaults("main")
    rows = re.findall(r"^\| `(\w+)` \| `([^`]+)` \|", DOC, re.MULTILINE)
    assert len(rows) == len(defaults) - 1  # region 另外在 2-1 說明
    for name, value in rows:
        assert defaults[name] == value, name


def test_zip_contents_in_doc_match_backend():
    line = re.search(r"預期列出 (\d+) 個檔案.*", DOC)
    listed = re.findall(r"`(\w+\.py)`", line.group(0))
    actual = sorted(p.name for p in SRC.glob("*.py"))
    assert sorted(listed) == actual
    assert int(line.group(1)) == len(actual)


def test_lambda_test_event_in_doc_returns_200():
    event = json.loads(re.search(r"@'\n(.*?)\n'@", POWERSHELL, re.DOTALL).group(1))
    assert handler.lambda_handler(event, None)["statusCode"] == 200


def test_terraform_flags_are_quoted_for_powershell():
    # PowerShell 會把 -out=main.tfplan 拆成 -out=main 和 .tfplan 兩個參數，
    # Terraform 會回 Too many command line arguments
    unquoted = re.findall(r'(?<!")-(?:out|chdir|backend-config|var)=\S*', POWERSHELL)
    assert unquoted == []
