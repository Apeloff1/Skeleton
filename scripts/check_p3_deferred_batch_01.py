#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
BATCH = Path("machine/ai_p3_deferred_batch_01.json")
SOURCE = Path("machine/ai_p3_training_execution_map.json")
MASTER = Path("machine/ai_master_plan.json")

EXPECTED_REFS = tuple(f"VOL-{number}" for number in range(153, 164))
EXPECTED_TASKS = {
    "P3D-MM-01": {"VOL-153", "VOL-154", "VOL-155", "VOL-156", "VOL-157", "VOL-158"},
    "P3D-RET-01": {"VOL-159"},
    "P3D-EXT-01": {"VOL-160", "VOL-161", "VOL-162"},
    "P3D-SEC-01": {"VOL-163"},
}
EXPECTED_DEPS = {
    "P3D-MM-01": [],
    "P3D-RET-01": ["P3D-MM-01"],
    "P3D-EXT-01": [],
    "P3D-SEC-01": ["P3D-EXT-01"],
}
FORBIDDEN_TERMINAL_STATUSES = {"closed", "complete", "completed", "verified", "promoted"}


class DeferredBatchValidationError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeferredBatchValidationError(f"cannot read {relative}") from exc
    if not isinstance(value, dict):
        raise DeferredBatchValidationError(f"{relative} must contain an object")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    batch = _load(root, BATCH)
    source = _load(root, SOURCE)
    master = _load(root, MASTER)

    if batch.get("schema_version") != "skeleton.ai.p3.deferred_batch.v1":
        raise DeferredBatchValidationError("deferred batch schema drift")
    if batch.get("batch_id") != "P3-DEFERRED-BATCH-01":
        raise DeferredBatchValidationError("deferred batch identity drift")
    if batch.get("phase") != "P3-T3":
        raise DeferredBatchValidationError("deferred batch phase drift")
    if batch.get("status") != "implemented_pending_validation":
        raise DeferredBatchValidationError("deferred batch status drift")

    source_meta = batch.get("source")
    if not isinstance(source_meta, dict):
        raise DeferredBatchValidationError("deferred batch source authority must be an object")
    expected_source = {
        "execution_map": str(SOURCE),
        "queue_pointer": "#/first_tranche/queued_volume_refs",
        "source_queue_count": 178,
        "source_is_frozen": True,
    }
    for key, expected in expected_source.items():
        if source_meta.get(key) != expected:
            raise DeferredBatchValidationError(f"deferred batch source authority drift: {key}")

    queue = source.get("first_tranche", {}).get("queued_volume_refs")
    if not isinstance(queue, list) or len(queue) != 178 or len(set(queue)) != 178:
        raise DeferredBatchValidationError("source P3-T2 deferred frontier must remain exactly 178 unique volumes")

    selection = batch.get("selection", {})
    selected = selection.get("volume_refs")
    if selected != list(EXPECTED_REFS):
        raise DeferredBatchValidationError("batch selection must remain the contiguous VOL-153..VOL-163 slice")
    if selection.get("selected_count") != 11:
        raise DeferredBatchValidationError("selected_count must be 11")
    if not set(selected).issubset(set(queue)):
        raise DeferredBatchValidationError("selected volumes must all belong to the frozen P3-T2 deferred queue")
    remaining = [ref for ref in queue if ref not in set(selected)]
    if len(remaining) != 167 or selection.get("projected_remaining_count") != 167:
        raise DeferredBatchValidationError("successor deferred projection must be 11 selected / 167 remaining")
    if set(remaining) | set(selected) != set(queue) or set(remaining) & set(selected):
        raise DeferredBatchValidationError("successor projection must preserve the source queue exactly")

    raw_tasks = batch.get("tasks")
    if not isinstance(raw_tasks, list):
        raise DeferredBatchValidationError("batch tasks must be a list")
    task_ids = [
        task.get("task_id")
        for task in raw_tasks
        if isinstance(task, dict) and task.get("task_id")
    ]
    if len(task_ids) != len(raw_tasks) or len(task_ids) != len(set(task_ids)):
        raise DeferredBatchValidationError("batch task IDs must be unique and non-empty")
    tasks = {task["task_id"]: task for task in raw_tasks}
    if set(tasks) != set(EXPECTED_TASKS):
        raise DeferredBatchValidationError("batch task inventory drift")

    owned: list[str] = []
    implementation_paths: set[str] = set()
    test_paths: set[str] = set()
    for task_id, expected_refs in EXPECTED_TASKS.items():
        task = tasks[task_id]
        refs = task.get("volume_refs")
        if not isinstance(refs, list) or set(refs) != expected_refs:
            raise DeferredBatchValidationError(f"{task_id} volume ownership drift")
        if task.get("depends_on") != EXPECTED_DEPS[task_id]:
            raise DeferredBatchValidationError(f"{task_id} dependency drift")
        owned.extend(refs)
        status = str(task.get("status", "")).lower()
        if status != "implemented_pending_validation":
            raise DeferredBatchValidationError(
                f"{task_id} status must remain implemented_pending_validation"
            )
        if (
            task.get("completion_checkbox") is not False
            or task.get("implementation_signed") is not False
            or task.get("verification_signed") is not False
        ):
            raise DeferredBatchValidationError(f"{task_id} may not self-complete or self-sign")
        declared_implementation = task.get("implementation_paths")
        declared_tests = task.get("test_paths")
        if (
            not isinstance(declared_implementation, list)
            or not declared_implementation
            or len(declared_implementation) != len(set(declared_implementation))
            or not all(isinstance(path, str) and path for path in declared_implementation)
        ):
            raise DeferredBatchValidationError(
                f"{task_id} implementation_paths must be unique non-empty paths"
            )
        if (
            not isinstance(declared_tests, list)
            or not declared_tests
            or len(declared_tests) != len(set(declared_tests))
            or not all(isinstance(path, str) and path for path in declared_tests)
        ):
            raise DeferredBatchValidationError(
                f"{task_id} test_paths must be unique non-empty paths"
            )
        implementation_paths.update(declared_implementation)
        test_paths.update(declared_tests)

    if len(owned) != 11 or len(set(owned)) != 11 or set(owned) != set(selected):
        raise DeferredBatchValidationError("every selected volume requires exactly one task owner")

    master_volumes = {
        item.get("key"): item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and item.get("key")
    }
    expected_contracts = batch.get("acceptance", {}).get("expected_contracts")
    if not isinstance(expected_contracts, dict) or set(expected_contracts) != set(selected):
        raise DeferredBatchValidationError("expected contract inventory must cover every selected volume")

    source_text = ""
    for relative in sorted(implementation_paths):
        path = root / relative
        if not path.is_file():
            raise DeferredBatchValidationError(f"missing implementation path: {relative}")
        source_text += "\n" + path.read_text(encoding="utf-8")
    for relative in sorted(test_paths):
        if not (root / relative).is_file():
            raise DeferredBatchValidationError(f"missing test path: {relative}")

    for ref in selected:
        volume = master_volumes.get(ref)
        if volume is None:
            raise DeferredBatchValidationError(f"masterplan volume missing: {ref}")
        master_contracts = volume.get("contracts")
        if expected_contracts.get(ref) != master_contracts:
            raise DeferredBatchValidationError(f"{ref} contract projection disagrees with canonical masterplan")
        if volume.get("completion_checkbox") is not False:
            raise DeferredBatchValidationError(f"{ref} canonical completion checkbox unexpectedly changed")
        for contract in master_contracts:
            if f"class {contract}" not in source_text:
                raise DeferredBatchValidationError(f"{ref} contract not materialized: {contract}")

    progress = batch.get("progress", {})
    if progress != {
        "selected_volume_count": 11,
        "projected_remaining_volume_count": 167,
        "task_count": 4,
        "validated": False,
        "merged": False,
    }:
        raise DeferredBatchValidationError("batch progress projection drift")

    return {
        "status": "valid",
        "batch_id": batch.get("batch_id"),
        "selected_volume_count": 11,
        "projected_remaining_volume_count": 167,
        "task_count": 4,
        "contract_count": sum(len(expected_contracts[ref]) for ref in selected),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(ROOT)
    except DeferredBatchValidationError as exc:
        print(f"P3 deferred batch 01: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "P3 deferred batch 01: OK "
            f"({result['selected_volume_count']} selected / "
            f"{result['projected_remaining_volume_count']} projected remaining; "
            f"{result['contract_count']} named contracts)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
