#!/usr/bin/env python3
"""Fail-closed P5 review. A clean bill with open findings is rejected."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skeleton.p5.review import run_review


def main() -> int:
    report = run_review()
    backlog = json.loads((ROOT / "machine/ai_p5_task_backlog.json").read_text())
    findings = report["open_findings"]
    if findings and backlog.get("status") != "reviewed_open":
        raise SystemExit("P5 must stay reviewed_open while findings exist")
    if not findings and backlog.get("status") != "reviewed_clear":
        raise SystemExit("P5 must be reviewed_clear when findings are empty")
    if any(task.get("completion_checkbox") for task in backlog["tasks"]):
        raise SystemExit("P5 task may not check completion")
    finding_ids = {row["id"] for row in report["open_findings"]}
    declared = {row["id"] for row in backlog["findings"]}
    if finding_ids != declared:
        raise SystemExit("P5 finding set drift")
    print(f"P5 review valid: probes={report['probes_held']} open={len(finding_ids)} clean={report['clean']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
