#!/usr/bin/env python3
"""Validate the canonical AI build queue as an executable dependency contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "machine" / "ai_build_queue.json"
CONSTRUCTION = ROOT / "machine" / "ai_app_construction.json"

ALLOWED_STATUSES = {
    "pending",
    "in_progress",
    "blocked",
    "evidence_pending",
    "done",
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain an object")
    return payload


def _nonempty_strings(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def validate(
    queue: dict[str, Any] | None = None,
    construction: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if queue is None:
        if not QUEUE.is_file():
            return ["machine/ai_build_queue.json is missing"]
        queue = _load(QUEUE)
    if construction is None:
        if not CONSTRUCTION.is_file():
            return ["machine/ai_app_construction.json is missing"]
        construction = _load(CONSTRUCTION)

    if queue.get("schema_version") != 1:
        errors.append("queue schema_version must equal 1")
    if queue.get("status") != "active":
        errors.append("queue status must remain active")
    if set(queue.get("status_values") or []) != ALLOWED_STATUSES:
        errors.append("queue status_values drifted from canonical lifecycle")

    tasks = queue.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return errors + ["queue tasks must be a non-empty list"]
    gaps = construction.get("gap_register")
    if not isinstance(gaps, list):
        return errors + ["construction gap_register must be a list"]
    gap_ids = {
        row.get("id")
        for row in gaps
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }

    ids = [
        task.get("task_id")
        for task in tasks
        if isinstance(task, dict)
    ]
    if len(ids) != len(tasks) or any(not isinstance(item, str) or not item for item in ids):
        errors.append("every queue task requires a non-empty task_id")
    if len(ids) != len(set(ids)):
        errors.append("queue task_id values must be unique")
    task_by_id = {
        task["task_id"]: task
        for task in tasks
        if isinstance(task, dict) and isinstance(task.get("task_id"), str)
    }

    for task in tasks:
        if not isinstance(task, dict):
            errors.append("queue tasks must be objects")
            continue
        task_id = str(task.get("task_id") or "?")
        if task.get("gap") not in gap_ids:
            errors.append(f"{task_id}: gap is not in construction gap_register")
        stage = task.get("stage")
        if isinstance(stage, bool) or not isinstance(stage, int) or stage < 0:
            errors.append(f"{task_id}: stage must be a non-negative integer")
        if not isinstance(task.get("parallel_lane"), str) or not task["parallel_lane"].strip():
            errors.append(f"{task_id}: parallel_lane must be non-empty")
        if not isinstance(task.get("objective"), str) or not task["objective"].strip():
            errors.append(f"{task_id}: objective must be non-empty")
        if task.get("status") not in ALLOWED_STATUSES:
            errors.append(f"{task_id}: invalid status")
        if not _nonempty_strings(task.get("target_paths")):
            errors.append(f"{task_id}: target_paths must be non-empty")
        if not _nonempty_strings(task.get("acceptance")):
            errors.append(f"{task_id}: acceptance must be non-empty")
        if not _nonempty_strings(task.get("work_package_refs")):
            errors.append(f"{task_id}: work_package_refs must be non-empty")
        if not isinstance(task.get("failure_rule"), str) or not task["failure_rule"].strip():
            errors.append(f"{task_id}: failure_rule must be non-empty")
        if not isinstance(task.get("done_when"), str) or not task["done_when"].strip():
            errors.append(f"{task_id}: done_when must be non-empty")
        if not isinstance(task.get("can_start_before_closure_dependencies_close"), bool):
            errors.append(
                f"{task_id}: can_start_before_closure_dependencies_close must be boolean"
            )

        dependencies = task.get("task_dependencies")
        if not isinstance(dependencies, list) or not all(
            isinstance(item, str) and item for item in dependencies
        ):
            errors.append(f"{task_id}: task_dependencies must be a string list")
            dependencies = []
        if task_id in dependencies:
            errors.append(f"{task_id}: task cannot depend on itself")
        for dependency_id in dependencies:
            dependency = task_by_id.get(dependency_id)
            if dependency is None:
                errors.append(f"{task_id}: unknown task dependency {dependency_id}")
                continue
            dep_stage = dependency.get("stage")
            if (
                isinstance(stage, int)
                and not isinstance(stage, bool)
                and isinstance(dep_stage, int)
                and not isinstance(dep_stage, bool)
                and dep_stage > stage
            ):
                errors.append(
                    f"{task_id}: dependency {dependency_id} is in a later stage"
                )
            if task.get("status") == "done" and dependency.get("status") != "done":
                errors.append(
                    f"{task_id}: done task depends on non-done {dependency_id}"
                )

        closure_dependencies = task.get("closure_dependencies")
        if not isinstance(closure_dependencies, list) or not all(
            isinstance(item, str) and item for item in closure_dependencies
        ):
            errors.append(f"{task_id}: closure_dependencies must be a string list")
            closure_dependencies = []
        for gap_id in closure_dependencies:
            if gap_id not in gap_ids:
                errors.append(f"{task_id}: unknown closure dependency {gap_id}")

        expected_accountability = f"ACC-{task_id}"
        if task.get("accountability_id") != expected_accountability:
            errors.append(
                f"{task_id}: accountability_id must equal {expected_accountability}"
            )
        if task.get("accountability_required") is not True:
            errors.append(f"{task_id}: accountability_required must be true")

        checked = task.get("completion_checkbox")
        mark = task.get("completion_checkbox_mark")
        expected_mark = "[x]" if checked is True else "[ ]"
        if checked not in (True, False):
            errors.append(f"{task_id}: completion_checkbox must be boolean")
        elif mark != expected_mark:
            errors.append(f"{task_id}: completion_checkbox_mark disagrees with checkbox")
        if task.get("status") == "done":
            if checked is not True:
                errors.append(f"{task_id}: done task must be checked")
            if task.get("implementation_signed") is not True:
                errors.append(f"{task_id}: done task needs implementation signoff")
            if task.get("verification_signed") is not True:
                errors.append(f"{task_id}: done task needs verification signoff")
        elif checked is True:
            errors.append(f"{task_id}: non-done task cannot be checked")

        engineering = task.get("engineering_inheritance")
        if not isinstance(engineering, dict):
            errors.append(f"{task_id}: engineering_inheritance must be an object")
        else:
            if engineering.get("task_id") != task_id:
                errors.append(f"{task_id}: engineering_inheritance task_id drifted")
            refs = engineering.get("engineering_profile_refs")
            if not isinstance(refs, list) or set(refs) != set(task.get("work_package_refs") or []):
                errors.append(
                    f"{task_id}: engineering profile refs disagree with work_package_refs"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str, stack: list[str]) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            cycle = " -> ".join(stack + [task_id])
            errors.append(f"queue task dependency cycle detected: {cycle}")
            return
        visiting.add(task_id)
        task = task_by_id.get(task_id, {})
        for dependency_id in task.get("task_dependencies") or []:
            if dependency_id in task_by_id:
                visit(dependency_id, stack + [task_id])
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_by_id:
        visit(task_id, [])

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("AI build queue: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    queue = _load(QUEUE)
    print(f"AI build queue: OK ({len(queue['tasks'])} tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
