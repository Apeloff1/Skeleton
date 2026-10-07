#!/usr/bin/env python3
"""Validate the activated P2-T1 partition and functional-AI ownership."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
PLAN = Path("machine/ai_p2_tranche1_plan.json")
MAP = Path("machine/ai_p2_execution_map.json")
BACKLOG = Path("machine/ai_p2_task_backlog.json")
CANONICAL = Path("scripts/check_p2_execution_map.py")

EXPECTED_TASKS = {
    "P2-T1-DATA-01": {"VOL-005", "VOL-039", "VOL-132", "VOL-134"},
    "P2-T1-SEC-01": {"VOL-026", "VOL-027", "VOL-167", "VOL-169", "VOL-172", "VOL-175"},
    "P2-T1-INFER-01": {"VOL-007"},
    "P2-T1-RECOVERY-01": {"VOL-091", "VOL-096"},
    "P2-T1-FUNCTIONAL-01": {"VOL-097", "VOL-104"},
}
EXPECTED_DEPS = {
    "P2-T1-DATA-01": ["P2-NATIVE-01"],
    "P2-T1-SEC-01": ["P2-NATIVE-01"],
    "P2-T1-INFER-01": ["P2-T1-SEC-01"],
    "P2-T1-RECOVERY-01": ["P2-T1-DATA-01", "P2-T1-SEC-01"],
    "P2-T1-FUNCTIONAL-01": [
        "P2-T1-DATA-01",
        "P2-T1-SEC-01",
        "P2-T1-INFER-01",
        "P2-T1-RECOVERY-01",
    ],
}


class P2T1ActivationError(RuntimeError):
    pass


def _load(root: Path, rel: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P2T1ActivationError(f"cannot read {rel}") from exc
    if not isinstance(value, dict):
        raise P2T1ActivationError(f"{rel} must contain an object")
    return value


def _canonical_validate(root: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("p2_canonical", root / CANONICAL)
    if spec is None or spec.loader is None:
        raise P2T1ActivationError("cannot load canonical P2 validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.validate(root))


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    plan = _load(root, PLAN)
    p2 = _load(root, MAP)
    backlog = _load(root, BACKLOG)

    if plan.get("status") != "activated":
        raise P2T1ActivationError("T1 plan must be activated")
    activation = plan.get("activation")
    if not isinstance(activation, dict) or activation.get("mode") != "applied":
        raise P2T1ActivationError("T1 activation mode must be applied")

    canonical = _canonical_validate(root)
    if canonical.get("status") != "valid":
        raise P2T1ActivationError("canonical P2 execution map is not valid")
    if canonical.get("source_volume_count") != 314:
        raise P2T1ActivationError("P2 source scope must remain 314")
    if canonical.get("scheduled_volume_count") != 57:
        raise P2T1ActivationError("activated scheduled count must be 57")
    if canonical.get("queued_volume_count") != 257:
        raise P2T1ActivationError("activated queued count must be 257")
    if canonical.get("task_count") != 12 or canonical.get("lane_count") != 12:
        raise P2T1ActivationError("activated task/lane inventory must be 12/12")

    tasks = {
        task.get("task_id"): task
        for task in backlog.get("tasks", [])
        if isinstance(task, dict) and task.get("task_id")
    }
    native = tasks.get("P2-NATIVE-01")
    if not isinstance(native, dict) or native.get("status") != "landed_unpromoted":
        raise P2T1ActivationError("P2-NATIVE-01 must be landed_unpromoted")
    native_evidence = set(map(str, native.get("evidence_refs", [])))
    required_native_prefixes = ("github:pr#2332", "git:merge:", "workflow:P2 Profile-Gated Acceleration@")
    for prefix in required_native_prefixes:
        if not any(ref.startswith(prefix) for ref in native_evidence):
            raise P2T1ActivationError(f"P2-NATIVE-01 missing evidence prefix: {prefix}")

    scheduled = set(p2["first_tranche"]["scheduled_volume_refs"])
    queued = set(p2["first_tranche"]["queued_volume_refs"])
    selected = set(plan["selection"]["selected_volume_refs"])
    if len(selected) != 15 or not selected <= scheduled or selected & queued:
        raise P2T1ActivationError("T1 selected volumes must be scheduled and not queued")

    for task_id, refs in EXPECTED_TASKS.items():
        task = tasks.get(task_id)
        if not isinstance(task, dict):
            raise P2T1ActivationError(f"missing activated task: {task_id}")
        if set(task.get("primary_volume_refs", [])) != refs:
            raise P2T1ActivationError(f"{task_id} ownership drift")
        if task.get("depends_on") != EXPECTED_DEPS[task_id]:
            raise P2T1ActivationError(f"{task_id} dependency drift")
        if task.get("completion_checkbox") is not False:
            raise P2T1ActivationError(f"{task_id} may not self-complete")
        if task.get("implementation_signed") is not False or task.get("verification_signed") is not False:
            raise P2T1ActivationError(f"{task_id} may not self-sign")

    return {
        "status": "valid",
        "source_volume_count": 314,
        "scheduled_volume_count": 57,
        "queued_volume_count": 257,
        "task_count": 12,
        "t1_task_count": 5,
        "functional_ai_task": "P2-T1-FUNCTIONAL-01",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(ROOT)
    except P2T1ActivationError as exc:
        print(f"P2 T1 activation: rejected: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("P2 T1 activation: OK (57 scheduled / 257 queued)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
