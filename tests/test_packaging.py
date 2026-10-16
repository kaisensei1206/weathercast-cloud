"""確認 Terraform 的 Lambda 設定和後端程式碼一致。

Terraform 直接把 backend/src 打包成 zip，不會另外安裝套件。
如果有人在後端 import 了第三方套件（例如 requests），本機測試會通過，部署後卻會 ImportError；
這裡在測試階段就把這種問題抓出來。
"""

import ast
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "backend" / "src"
LAMBDA_TF = (ROOT / "terraform" / "main" / "lambda.tf").read_text(encoding="utf-8")

# Lambda 的 Python 執行環境內建 boto3，不需要打包
PROVIDED_BY_LAMBDA = {"boto3", "botocore"}


def tf_setting(name: str) -> str:
    return re.search(rf'^\s*{name}\s*=\s*"([^"]+)"', LAMBDA_TF, re.MULTILINE).group(1)


def test_zip_is_built_from_backend_src():
    assert tf_setting("source_dir") == "${path.module}/../../backend/src"


def test_handler_setting_points_to_existing_function():
    module_name, function_name = tf_setting("handler").rsplit(".", 1)

    assert (SRC / f"{module_name}.py").is_file()
    assert callable(getattr(importlib.import_module(module_name), function_name))


def test_runtime_matches_local_python_version():
    local = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert tf_setting("runtime") == f"python{local}"


def imported_top_level_modules(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_backend_only_imports_what_the_zip_or_runtime_provides():
    local_modules = {p.stem for p in SRC.glob("*.py")}
    allowed = set(sys.stdlib_module_names) | local_modules | PROVIDED_BY_LAMBDA

    for path in sorted(SRC.glob("*.py")):
        missing = imported_top_level_modules(path) - allowed
        assert not missing, f"{path.name} 使用了不會被打包的套件：{missing}"
