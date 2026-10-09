#!/usr/bin/env python3
"""Fail-closed validator for the P4 production plane."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    backlog = json.loads((ROOT / "machine/ai_p4_task_backlog.json").read_text())
    p4 = json.loads((ROOT / "machine/ai_p4_execution_map.json").read_text())
    master = json.loads((ROOT / "machine/ai_master_plan.json").read_text())
    vols = {v["key"]: v for v in master["volumes"]}
    tasks = backlog["tasks"]
    if len(tasks) != 6:
        raise SystemExit("P4 task count drift")
    scheduled = []
    for task in tasks:
        if task["status"] != "closed":
            raise SystemExit(f"{task['task_id']} is not closed")
        if not (task["implementation_signed"] and task["verification_signed"] and task["completion_checkbox"]):
            raise SystemExit(f"{task['task_id']} missing signoff")
        if len(task.get("evidence_refs") or []) < 3:
            raise SystemExit(f"{task['task_id']} missing evidence")
        scheduled.extend(task["primary_volume_refs"])
    if scheduled != p4["first_tranche"]["scheduled_volume_refs"]:
        raise SystemExit("P4 ownership drift")
    if len(scheduled) != len(set(scheduled)):
        raise SystemExit("P4 volume owned twice")
    for ref in scheduled:
        volume = vols[ref]
        if volume.get("implementation_status") != "verified" or volume.get("completion_checkbox") is not True:
            raise SystemExit(f"{ref} is not a verified masterplan volume")
    if p4["progress"]["closed_tasks"] != [t["task_id"] for t in tasks]:
        raise SystemExit("P4 progress drift")
    print(f"P4 execution map valid: {len(scheduled)} scheduled, {len(tasks)} closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
