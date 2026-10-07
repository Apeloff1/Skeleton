#!/usr/bin/env python3
"""Fail-closed validation for the canonical P3 execution map and task backlog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
P2_MAP = Path("machine/ai_p2_execution_map.json")
P2_CLOSURE = Path("machine/ai_p2_functional_ai_closure.json")
P3_PLAN = Path("machine/ai_p3_tranche0_plan.json")
P3_MAP = Path("machine/ai_p3_execution_map.json")
P3_BACKLOG = Path("machine/ai_p3_task_backlog.json")

EXPECTED_SELECTED = {
    "P3-MODEL-FOUNDATION-01": {"VOL-001", "VOL-006", "VOL-019", "VOL-020"},
    "P3-DOMAIN-INTELLIGENCE-01": {"VOL-071", "VOL-072", "VOL-073", "VOL-074"},
    "P3-TRUST-EXPERIENCE-01": {"VOL-085", "VOL-086", "VOL-087", "VOL-088"},
    "P3-VERTICAL-SUITE-01": {"VOL-098", "VOL-099", "VOL-100", "VOL-101", "VOL-102", "VOL-103"},
    "P3-ACCEPTANCE-01": {"VOL-105", "VOL-106", "VOL-107"},
    "P3-CONSTRUCTION-AUTHORITY-01": {"VOL-111", "VOL-114"},
}
EXPECTED_DEPS = {
    "P3-MODEL-FOUNDATION-01": [],
    "P3-DOMAIN-INTELLIGENCE-01": ["P3-MODEL-FOUNDATION-01"],
    "P3-TRUST-EXPERIENCE-01": ["P3-MODEL-FOUNDATION-01"],
    "P3-VERTICAL-SUITE-01": [
        "P3-MODEL-FOUNDATION-01",
        "P3-DOMAIN-INTELLIGENCE-01",
        "P3-TRUST-EXPERIENCE-01",
    ],
    "P3-ACCEPTANCE-01": ["P3-VERTICAL-SUITE-01"],
    "P3-CONSTRUCTION-AUTHORITY-01": [
        "P3-TRUST-EXPERIENCE-01",
        "P3-ACCEPTANCE-01",
    ],
}
OBLIGATION_FIELDS = (
    "title",
    "depth_pass",
    "accountability_id",
    "implementation_status",
    "completion_checkbox",
    "signing_required",
    "contracts",
    "risks",
    "gaps",
    "implementation_paths",
    "tests",
    "evaluations",
)


class P3ValidationError(RuntimeError):
    pass


def _load(root: Path, rel: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P3ValidationError(f"cannot read {rel}") from exc
    if not isinstance(value, dict):
        raise P3ValidationError(f"{rel} must contain an object")
    return value


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dup: set[str] = set()
    for value in values:
        if value in seen:
            dup.add(value)
        seen.add(value)
    return sorted(dup)


def _assert_acyclic(tasks: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str, stack: list[str]) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise P3ValidationError(
                "P3 task dependency cycle: " + " -> ".join(stack + [task_id])
            )
        visiting.add(task_id)
        task = tasks[task_id]
        for dep in task.get("depends_on", []):
            if dep not in tasks:
                raise P3ValidationError(f"{task_id} depends on unknown task {dep}")
            visit(dep, stack + [task_id])
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in sorted(tasks):
        visit(task_id, [])


def _expected_obligation(volume: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"volume_ref": volume["key"]}
    for field in OBLIGATION_FIELDS:
        result[field] = volume.get(field)
    return result


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    master = _load(root, MASTER)
    p2 = _load(root, P2_MAP)
    p2_closure = _load(root, P2_CLOSURE)
    plan = _load(root, P3_PLAN)
    p3 = _load(root, P3_MAP)
    backlog = _load(root, P3_BACKLOG)

    if p2_closure.get("status") != "closed":
        raise P3ValidationError("P3 requires closed P2 Functional-AI frontier")
    if p2_closure.get("closure_id") != "P2-FUNCTIONAL-AI-FRONTIER":
        raise P3ValidationError("P2 Functional-AI closure identity drift")
    if p3.get("status") != "active" or backlog.get("status") != "active":
        raise P3ValidationError("P3 map/backlog must be active")
    if plan.get("status") != "active":
        raise P3ValidationError("P3 T0 plan must be active")
    if master.get("status") != p3.get("masterplan_alignment", {}).get(
        "required_master_status"
    ):
        raise P3ValidationError("P3 required master status drift")
    if master.get("plan_version") != p3.get("masterplan_alignment", {}).get(
        "required_plan_version"
    ):
        raise P3ValidationError("P3 required master plan version drift")
    if master.get("breadth_freeze") != p3.get("masterplan_alignment", {}).get(
        "breadth_freeze"
    ):
        raise P3ValidationError("P3 breadth-freeze authority drift")
    if master.get("volume_maturity_policy") != p3.get(
        "masterplan_alignment", {}
    ).get("volume_maturity_policy"):
        raise P3ValidationError("P3 maturity-policy authority drift")

    source = p3.get("source_scope", {}).get("volume_refs")
    parent_queue = p2.get("first_tranche", {}).get("queued_volume_refs")
    if not isinstance(source, list) or not isinstance(parent_queue, list):
        raise P3ValidationError("P3/P2 source queues must be lists")
    if source != parent_queue:
        missing = sorted(set(parent_queue) - set(source))
        extra = sorted(set(source) - set(parent_queue))
        raise P3ValidationError(
            f"P3 source must exactly equal P2 queued scope; missing={missing}, extra={extra}"
        )
    if len(source) != 257 or len(set(source)) != 257:
        raise P3ValidationError("P3 source scope must contain 257 unique refs")
    if p3.get("source_scope", {}).get("expected_volume_count") != 257:
        raise P3ValidationError("P3 source expected count drift")

    tranche = p3.get("first_tranche")
    if not isinstance(tranche, dict):
        raise P3ValidationError("P3 first_tranche missing")
    scheduled = tranche.get("scheduled_volume_refs")
    queued = tranche.get("queued_volume_refs")
    if not isinstance(scheduled, list) or not isinstance(queued, list):
        raise P3ValidationError("P3 scheduled/queued refs must be lists")
    if _duplicates(scheduled) or _duplicates(queued):
        raise P3ValidationError("P3 scheduled/queued refs must be unique")
    if set(scheduled) & set(queued):
        raise P3ValidationError("P3 scheduled/queued overlap")
    if set(scheduled) | set(queued) != set(source):
        raise P3ValidationError("P3 scheduled+queued must cover source exactly")
    if len(scheduled) != 23 or tranche.get("scheduled_volume_count") != 23:
        raise P3ValidationError("P3 T0 scheduled count must be 23")
    if len(queued) != 234 or tranche.get("queued_volume_count") != 234:
        raise P3ValidationError("P3 T0 queued count must be 234")

    selected = set().union(*EXPECTED_SELECTED.values())
    if set(scheduled) != selected:
        raise P3ValidationError("P3 T0 selected volume set drift")
    if plan.get("selection", {}).get("selected_volume_refs") != scheduled:
        raise P3ValidationError("P3 plan/map selected-volume ordering drift")
    if plan.get("selection", {}).get("selected_volume_count") != 23:
        raise P3ValidationError("P3 plan selected count drift")
    if plan.get("selection", {}).get("remaining_queued_volume_count") != 234:
        raise P3ValidationError("P3 plan queued count drift")

    volumes = {
        item.get("key"): item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    if not set(source) <= set(volumes):
        raise P3ValidationError("P3 references unknown masterplan volumes")

    task_rows = backlog.get("tasks")
    if not isinstance(task_rows, list) or len(task_rows) != 6:
        raise P3ValidationError("P3 T0 backlog must contain six tasks")
    tasks = {
        task.get("task_id"): task
        for task in task_rows
        if isinstance(task, dict) and isinstance(task.get("task_id"), str)
    }
    if set(tasks) != set(EXPECTED_SELECTED) or len(tasks) != len(task_rows):
        raise P3ValidationError("P3 T0 task inventory drift")
    _assert_acyclic(tasks)

    owned: list[str] = []
    for task_id, expected_refs in EXPECTED_SELECTED.items():
        task = tasks[task_id]
        refs = task.get("primary_volume_refs")
        if not isinstance(refs, list) or set(refs) != expected_refs:
            raise P3ValidationError(f"{task_id} owned-volume drift")
        owned.extend(refs)
        if task.get("depends_on") != EXPECTED_DEPS[task_id]:
            raise P3ValidationError(f"{task_id} dependency drift")
        if task.get("priority") != "P3":
            raise P3ValidationError(f"{task_id} priority drift")
        if task.get("accountability_required") is not True:
            raise P3ValidationError(f"{task_id} lost accountability requirement")
        if (
            task.get("completion_checkbox") is not False
            or task.get("completion_checkbox_mark") != "[ ]"
            or task.get("implementation_signed") is not False
            or task.get("verification_signed") is not False
        ):
            raise P3ValidationError(f"{task_id} may not self-complete or self-sign")
        evidence = task.get("evidence_refs")
        if not isinstance(evidence, list) or len(evidence) < 3:
            raise P3ValidationError(f"{task_id} requires source evidence refs")

        obligations = task.get("masterplan_obligations")
        if not isinstance(obligations, list) or len(obligations) != len(refs):
            raise P3ValidationError(f"{task_id} obligation coverage drift")
        by_ref = {
            item.get("volume_ref"): item
            for item in obligations
            if isinstance(item, dict)
        }
        if set(by_ref) != set(refs) or len(by_ref) != len(obligations):
            raise P3ValidationError(f"{task_id} obligation identity drift")
        for ref in refs:
            if by_ref[ref] != _expected_obligation(volumes[ref]):
                raise P3ValidationError(
                    f"{task_id} narrows/drifts canonical masterplan obligation {ref}"
                )

    if len(owned) != 23 or len(set(owned)) != 23 or set(owned) != set(scheduled):
        raise P3ValidationError("P3 T0 scheduled volumes require exactly one task owner")

    landed = {
        task_id
        for task_id, task in tasks.items()
        if task.get("status") == "landed_unpromoted"
    }
    allowed_status = {"blocked", "ready", "in_progress", "landed_unpromoted"}
    for task_id, task in tasks.items():
        status = task.get("status")
        if status not in allowed_status:
            raise P3ValidationError(f"{task_id} unsupported status {status!r}")
        deps = task.get("depends_on", [])
        unresolved = [dep for dep in deps if dep not in landed]
        if status == "blocked" and not unresolved:
            raise P3ValidationError(
                f"{task_id} blocked even though all dependencies are landed"
            )
        if status in {"ready", "in_progress", "landed_unpromoted"} and unresolved:
            raise P3ValidationError(
                f"{task_id} {status} with unresolved dependencies {unresolved}"
            )
        if status == "landed_unpromoted" and len(task.get("evidence_refs", [])) < 4:
            raise P3ValidationError(
                f"{task_id} landed_unpromoted requires implementation evidence"
            )

    summary = backlog.get("summary")
    if not isinstance(summary, dict):
        raise P3ValidationError("P3 backlog summary missing")
    expected_summary = {
        "task_count": len(tasks),
        "in_progress_count": sum(t.get("status") == "in_progress" for t in tasks.values()),
        "ready_count": sum(t.get("status") == "ready" for t in tasks.values()),
        "blocked_count": sum(t.get("status") == "blocked" for t in tasks.values()),
        "landed_unpromoted_count": sum(
            t.get("status") == "landed_unpromoted" for t in tasks.values()
        ),
        "scheduled_volume_count": 23,
        "queued_volume_count": 234,
        "source_volume_count": 257,
    }
    if summary != expected_summary:
        raise P3ValidationError(
            f"P3 backlog summary drift: {summary!r} != {expected_summary!r}"
        )
    if p3.get("progress") != expected_summary:
        raise P3ValidationError("P3 execution-map progress drift")

    return {
        "status": "valid",
        "source_volume_count": 257,
        "scheduled_volume_count": 23,
        "queued_volume_count": 234,
        "task_count": 6,
        "ready_count": expected_summary["ready_count"],
        "blocked_count": expected_summary["blocked_count"],
        "parent_functional_frontier": "closed",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(Path(args.repo_root))
    except P3ValidationError as exc:
        print(f"P3 execution map: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "P3 execution map: OK "
            f"({result['scheduled_volume_count']} scheduled / "
            f"{result['queued_volume_count']} queued)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
