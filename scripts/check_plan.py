"""檢查 terraform plan 是否只更新 Lambda，CD 用它決定能不能自動部署。

GitHub Actions 的部署角色只有「更新 Lambda」的權限。plan 裡如果出現其他變更
（新增資源、改 IAM、刪除資料表……），代表這次合併改到了基礎設施，應該由人在本機
檢查 plan 後 apply，而不是讓 CI 自動執行。

用法（在 terraform/main）：
  terraform show -json main.tfplan > plan.json
  python ../../scripts/check_plan.py plan.json

結束代碼：0 = 沒有變更或只更新 Lambda，可以 apply；1 = 有其他變更，停止部署。
"""

import json
import sys
from pathlib import Path

# CD 唯一可以自動執行的變更
ALLOWED = {("aws_lambda_function.api", ("update",))}


def planned_changes(plan: dict) -> list[tuple[str, tuple[str, ...]]]:
    """列出會改變的資源；沒有變更（no-op）和 data source 的讀取不算。"""
    changes = []
    for rc in plan.get("resource_changes", []):
        actions = tuple(rc["change"]["actions"])
        if rc.get("mode") == "data" or actions == ("no-op",):
            continue
        changes.append((rc["address"], actions))
    return changes


def disallowed(changes: list[tuple[str, tuple[str, ...]]]) -> list[tuple[str, tuple[str, ...]]]:
    return [c for c in changes if c not in ALLOWED]


def main(argv: list[str]) -> int:
    plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    changes = planned_changes(plan)
    blocked = disallowed(changes)

    for address, actions in changes:
        mark = "BLOCKED" if (address, actions) in blocked else "ok"
        print(f"[{mark}] {','.join(actions):<16} {address}")

    if blocked:
        print(
            "Plan changes infrastructure, not just Lambda code. "
            "Review and apply it locally (docs/deployment.md), then re-run this workflow."
        )
        return 1
    print("No changes." if not changes else "Only Lambda code/config changes. Safe to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
