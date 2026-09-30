#!/usr/bin/env python3
"""Fail-closed validator for the P2 execution foundation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


class P2ValidationError(RuntimeError):
    pass


def _load(root: Path, relative: str) -> dict:
    path = root / relative
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise P2ValidationError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise P2ValidationError(f"invalid JSON in {relative}: {exc}") from exc


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for value in values:
        if value in seen:
            dupes.add(value)
        seen.add(value)
    return sorted(dupes)


def _assert_acyclic(nodes: set[str], edges: dict[str, list[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            cycle = " -> ".join(path + [node])
            raise P2ValidationError(f"{label} dependency cycle: {cycle}")
        visiting.add(node)
        for dep in edges.get(node, []):
            if dep not in nodes:
                raise P2ValidationError(f"{label} {node} depends on unknown node {dep}")
            visit(dep, path + [node])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(nodes):
        visit(node, [])


def validate(root: Path) -> dict:
    master = _load(root, "machine/ai_master_plan.json")
    p1 = _load(root, "machine/ai_p1_execution_map.json")
    p2 = _load(root, "machine/ai_p2_execution_map.json")
    backlog = _load(root, "machine/ai_p2_task_backlog.json")

    master_refs = {v["key"] for v in master.get("volumes", [])}
    p1_deferred = p1.get("scope_summary", {}).get("deferred_volume_refs", [])
    p2_source = p2.get("source_scope", {}).get("volume_refs", [])

    if len(p1_deferred) != 314:
        raise P2ValidationError(f"P1 deferred scope drift: expected 314, got {len(p1_deferred)}")
    if _duplicates(p1_deferred):
        raise P2ValidationError(f"duplicate P1 deferred refs: {_duplicates(p1_deferred)}")
    if _duplicates(p2_source):
        raise P2ValidationError(f"duplicate P2 source refs: {_duplicates(p2_source)}")
    if set(p2_source) != set(p1_deferred):
        missing = sorted(set(p1_deferred) - set(p2_source))
        extra = sorted(set(p2_source) - set(p1_deferred))
        raise P2ValidationError(f"P2 source must equal P1 deferred scope; missing={missing}, extra={extra}")
    unknown_master = sorted(set(p2_source) - master_refs)
    if unknown_master:
        raise P2ValidationError(f"P2 references unknown masterplan volumes: {unknown_master}")

    tranche = p2.get("first_tranche", {})
    scheduled = tranche.get("scheduled_volume_refs", [])
    queued = tranche.get("queued_volume_refs", [])
    if _duplicates(scheduled):
        raise P2ValidationError(f"duplicate scheduled refs: {_duplicates(scheduled)}")
    if _duplicates(queued):
        raise P2ValidationError(f"duplicate queued refs: {_duplicates(queued)}")
    overlap = sorted(set(scheduled) & set(queued))
    if overlap:
        raise P2ValidationError(f"scheduled/queued overlap: {overlap}")
    if set(scheduled) | set(queued) != set(p2_source):
        missing = sorted(set(p2_source) - (set(scheduled) | set(queued)))
        extra = sorted((set(scheduled) | set(queued)) - set(p2_source))
        raise P2ValidationError(f"scheduled+queued must cover P2 source exactly; missing={missing}, extra={extra}")
    if tranche.get("scheduled_volume_count") != len(scheduled):
        raise P2ValidationError("scheduled_volume_count mismatch")
    if tranche.get("queued_volume_count") != len(queued):
        raise P2ValidationError("queued_volume_count mismatch")
    if p2.get("source_scope", {}).get("expected_volume_count") != len(p2_source):
        raise P2ValidationError("expected_volume_count mismatch")

    tasks = backlog.get("tasks", [])
    task_ids = [t.get("task_id") for t in tasks]
    if any(not t for t in task_ids):
        raise P2ValidationError("every task requires task_id")
    if _duplicates(task_ids):
        raise P2ValidationError(f"duplicate task ids: {_duplicates(task_ids)}")

    task_nodes = set(task_ids)
    task_edges = {t["task_id"]: list(t.get("depends_on", [])) for t in tasks}
    for task_id, deps in task_edges.items():
        if task_id in deps:
            raise P2ValidationError(f"task {task_id} cannot depend on itself")
    _assert_acyclic(task_nodes, task_edges, "task")

    owned_refs = [ref for t in tasks for ref in t.get("primary_volume_refs", [])]
    if _duplicates(owned_refs):
        raise P2ValidationError(f"scheduled primary volume has multiple owners: {_duplicates(owned_refs)}")
    if set(owned_refs) != set(scheduled):
        missing = sorted(set(scheduled) - set(owned_refs))
        extra = sorted(set(owned_refs) - set(scheduled))
        raise P2ValidationError(f"task ownership must equal scheduled set; missing={missing}, extra={extra}")
    outside = sorted(set(owned_refs) - set(p2_source))
    if outside:
        raise P2ValidationError(f"task owns non-P2 volumes: {outside}")

    for task in tasks:
        if task.get("completion_checkbox") is not False:
            raise P2ValidationError(f"foundation task {task['task_id']} may not assert completion")
        if task.get("completion_checkbox_mark") != "[ ]":
            raise P2ValidationError(f"foundation task {task['task_id']} has invalid checkbox mark")
        if task.get("implementation_signed") is not False or task.get("verification_signed") is not False:
            raise P2ValidationError(f"foundation task {task['task_id']} may not fabricate sign-off")

    lanes = p2.get("lanes", [])
    lane_ids = [lane.get("id") for lane in lanes]
    if any(not lane for lane in lane_ids):
        raise P2ValidationError("every lane requires id")
    if _duplicates(lane_ids):
        raise P2ValidationError(f"duplicate lane ids: {_duplicates(lane_ids)}")
    lane_nodes = set(lane_ids)
    lane_edges = {lane["id"]: list(lane.get("depends_on", [])) for lane in lanes}
    _assert_acyclic(lane_nodes, lane_edges, "lane")
    unknown_task_lanes = sorted({t.get("lane_id") for t in tasks} - lane_nodes)
    if unknown_task_lanes:
        raise P2ValidationError(f"tasks reference unknown lanes: {unknown_task_lanes}")

    summary = backlog.get("summary", {})
    expected_counts = {
        "task_count": len(tasks),
        "in_progress_count": sum(t.get("status") == "in_progress" for t in tasks),
        "ready_count": sum(t.get("status") == "ready" for t in tasks),
        "blocked_count": sum(t.get("status") == "blocked" for t in tasks),
        "scheduled_volume_count": len(scheduled),
        "queued_volume_count": len(queued),
        "source_volume_count": len(p2_source),
    }
    for key, value in expected_counts.items():
        if summary.get(key) != value:
            raise P2ValidationError(f"backlog summary {key}={summary.get(key)!r}, expected {value!r}")

    baseline = p2.get("baseline", {}).get("p1_governed_frontier", {})
    if baseline != {"total": 513, "resolved": 513, "blocking_unresolved": 0, "unclassified": 0}:
        raise P2ValidationError(f"unexpected P1 baseline frontier: {baseline!r}")

    return {
        "source_volume_count": len(p2_source),
        "scheduled_volume_count": len(scheduled),
        "queued_volume_count": len(queued),
        "task_count": len(tasks),
        "lane_count": len(lanes),
        "status": "valid",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate(Path(args.repo_root).resolve())
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "P2 execution map valid: "
            f"{result['source_volume_count']} source, "
            f"{result['scheduled_volume_count']} scheduled, "
            f"{result['queued_volume_count']} queued, "
            f"{result['task_count']} tasks, {result['lane_count']} lanes"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
