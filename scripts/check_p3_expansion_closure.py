#!/usr/bin/env python3
"""Validate the bounded P3 autonomous-intelligence expansion closure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/ai_p3_expansion_closure.json")
PARENT = Path("machine/ai_p2_functional_ai_closure.json")
MAP = Path("machine/ai_p3_execution_map.json")
BACKLOG = Path("machine/ai_p3_task_backlog.json")


class P3ClosureError(RuntimeError):
    pass


def _load(root: Path, rel: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P3ClosureError(f"cannot read {rel}") from exc
    if not isinstance(value, dict):
        raise P3ClosureError(f"{rel} must contain an object")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    closure = _load(root, MANIFEST)
    parent = _load(root, PARENT)
    p3 = _load(root, MAP)
    backlog = _load(root, BACKLOG)

    if closure.get("status") not in {"candidate", "closed"}:
        raise P3ClosureError("P3 closure status must be candidate or closed")
    if closure.get("claim_scope") != "bounded_autonomous_intelligence_expansion_frontier":
        raise P3ClosureError("P3 closure claim scope drift")
    if parent.get("status") != "closed":
        raise P3ClosureError("P3 closure requires closed P2 Functional-AI frontier")

    source = p3.get("source_scope", {})
    first = p3.get("first_tranche", {})
    scheduled = first.get("scheduled_volume_refs")
    queued = first.get("queued_volume_refs")
    if not isinstance(scheduled, list) or not isinstance(queued, list):
        raise P3ClosureError("P3 scheduled/queued scope must be lists")
    if source.get("expected_volume_count") != 257 or len(source.get("volume_refs", [])) != 257:
        raise P3ClosureError("P3 source scope must remain 257")
    if len(scheduled) != 23 or len(queued) != 234:
        raise P3ClosureError("P3 bounded closure partition must remain 23/234")
    if set(scheduled) & set(queued):
        raise P3ClosureError("P3 scheduled and queued scopes overlap")
    if set(scheduled) | set(queued) != set(source.get("volume_refs", [])):
        raise P3ClosureError("P3 scheduled+queued must preserve the 257-volume source")

    frontier = closure.get("frontier")
    if not isinstance(frontier, dict):
        raise P3ClosureError("P3 closure frontier missing")
    if frontier.get("scheduled_volume_count") != 23 or frontier.get("queued_volume_count") != 234:
        raise P3ClosureError("P3 closure frontier counts drift")
    if frontier.get("scheduled_volume_refs") != scheduled:
        raise P3ClosureError("P3 closure scheduled-volume identity drift")

    tasks = backlog.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 6:
        raise P3ClosureError("P3 closure requires exactly six T0 tasks")
    ids = [task.get("task_id") for task in tasks if isinstance(task, dict)]
    if frontier.get("task_ids") != ids:
        raise P3ClosureError("P3 closure task identity drift")
    for task in tasks:
        task_id = task.get("task_id")
        if task.get("status") != "landed_unpromoted":
            raise P3ClosureError(f"{task_id} is not evidence-landed")
        if (
            task.get("completion_checkbox") is not False
            or task.get("implementation_signed") is not False
            or task.get("verification_signed") is not False
        ):
            raise P3ClosureError(f"{task_id} may not self-complete or self-sign")
        evidence = task.get("evidence_refs")
        if not isinstance(evidence, list) or len(evidence) < 4:
            raise P3ClosureError(f"{task_id} lacks executable evidence")

    progress = p3.get("progress")
    expected_progress = {
        "task_count": 6,
        "in_progress_count": 0,
        "ready_count": 0,
        "blocked_count": 0,
        "landed_unpromoted_count": 6,
        "scheduled_volume_count": 23,
        "queued_volume_count": 234,
        "source_volume_count": 257,
    }
    if backlog.get("summary") != expected_progress or progress != expected_progress:
        raise P3ClosureError("P3 terminal progress projection drift")

    critical = set(closure.get("critical_volume_refs", []))
    required_critical = {
        "VOL-098","VOL-099","VOL-100","VOL-101","VOL-102","VOL-103",
        "VOL-105","VOL-106","VOL-107","VOL-111","VOL-114",
    }
    if critical != required_critical or not critical <= set(scheduled):
        raise P3ClosureError("P3 critical acceptance/construction coverage drift")

    deferred = closure.get("deferred_scope", {})
    if deferred.get("queued_volume_count") != 234:
        raise P3ClosureError("P3 deferred scope must preserve 234 queued volumes")
    handoff = closure.get("handoff", {})
    if handoff.get("next_pr") != "#2348" or handoff.get("mode") != "stacked":
        raise P3ClosureError("P3 closure handoff must target stacked #2348")

    evidence = closure.get("evidence_refs")
    if not isinstance(evidence, list) or len(evidence) < 8:
        raise P3ClosureError("P3 closure requires implementation evidence refs")

    closure_evidence = closure.get("closure_evidence")
    if not isinstance(closure_evidence, list):
        raise P3ClosureError("P3 closure_evidence must be a list")
    if closure.get("status") == "closed":
        if len(closure_evidence) < 3:
            raise P3ClosureError("closed P3 frontier requires exact-head closure evidence")
        if not any(str(ref).startswith("workflow:P3 Expansion Closure@") for ref in closure_evidence):
            raise P3ClosureError("closed P3 frontier requires closure workflow evidence")

    return {
        "status": "valid",
        "closure_status": closure["status"],
        "source_volume_count": 257,
        "scheduled_volume_count": 23,
        "queued_volume_count": 234,
        "landed_task_count": 6,
        "handoff": "#2348",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(ROOT)
    except P3ClosureError as exc:
        print(f"P3 expansion closure: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "P3 expansion closure: OK "
            f"({result['scheduled_volume_count']} landed / {result['queued_volume_count']} deferred)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
