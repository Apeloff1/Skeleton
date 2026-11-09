#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTIER = ROOT / "machine" / "ai_execution_frontier_20260924.json"
LEDGER = ROOT / "machine" / "ai_build_accountability.json"
DOC = ROOT / "docs" / "plan" / "EXECUTION_FRONTIER_2026-09-24.md"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def validate() -> None:
    frontier = json.loads(FRONTIER.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    doc = DOC.read_text(encoding="utf-8")

    assert frontier["schema_version"] == "ai-execution-frontier/v1"
    assert frontier["authority"]["breadth_freeze"] == "VOL-420"
    assert SHA40.fullmatch(frontier["baseline_git_sha"])
    assert "No task is promoted by prose" in doc

    queue = [r for r in ledger["records"] if r.get("type") == "queue_task"]
    assert len(queue) == frontier["queue_snapshot"]["total"] == 42
    counts: dict[str, int] = {}
    for record in queue:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    for state in ("done", "evidence_pending", "in_progress", "pending"):
        assert counts.get(state, 0) == frontier["queue_snapshot"][state]

    by_id = {r["id"]: r for r in queue}
    candidates = frontier["promotion_candidates"]
    assert len(candidates) == frontier["landed_candidate_summary"]["task_count"]
    assert len(candidates) >= 22
    assert frontier["landed_candidate_summary"]["through_stage"] >= 3

    candidate_tasks: set[str] = set()
    for candidate in candidates:
        aid = candidate["accountability_id"]
        task_id = candidate["task_id"]
        assert aid in by_id, aid
        assert by_id[aid]["status"] == candidate["ledger_status"], aid
        assert candidate["target_next_lifecycle_state"] != "done"
        assert candidate["required_checks"], aid
        assert task_id not in candidate_tasks, task_id
        candidate_tasks.add(task_id)
        for sha in candidate["landed_commits"]:
            assert SHA40.fullmatch(sha), (aid, sha)

    wave_ids = {w["id"] for w in frontier["waves"]}
    seen_tasks: set[str] = set()
    for wave in frontier["waves"]:
        for dep in wave["depends_on"]:
            assert dep in wave_ids, (wave["id"], dep)
        for task_id in wave["tasks"]:
            aid = "ACC-" + task_id
            assert aid in by_id, (wave["id"], task_id)
            assert task_id not in seen_tasks, ("task repeated across frontier waves", task_id)
            seen_tasks.add(task_id)

    assert "AIQ-S1-MEM-03" in seen_tasks
    assert candidate_tasks.issubset(seen_tasks)
    assert frontier["waves"][0]["id"] == "EF-W0"
    assert frontier["waves"][-1]["id"] == "EF-W6"
    assert len(frontier["required_fault_families"]) >= 12
    assert any("independent verification" in x for x in frontier["lifecycle_rules"])


if __name__ == "__main__":
    validate()
    print("ai execution frontier: OK")
