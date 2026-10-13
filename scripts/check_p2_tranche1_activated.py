#!/usr/bin/env python3
"""Validate the activated P2-T1 partition and functional-AI ownership."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
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


def _check_task_state(
    task_id: str,
    task: dict[str, Any],
    *,
    pr: str,
    workflow: str,
    require_matching_head: bool = True,
) -> None:
    """Separate task activation from subsequent, evidence-backed signoff."""
    status = task.get("status")
    if status == "landed_unpromoted":
        if any(task.get(flag) is not False for flag in (
            "completion_checkbox", "implementation_signed", "verification_signed"
        )):
            raise P2T1ActivationError(f"{task_id} may not self-sign or self-complete")
        if task.get("completion_checkbox_mark") not in (None, "[ ]"):
            raise P2T1ActivationError(f"{task_id} unpromoted marker is checked")
        return

    if status != "closed":
        raise P2T1ActivationError(f"{task_id} must be unsigned or evidence-closed")
    if any(task.get(flag) is not True for flag in (
        "completion_checkbox", "implementation_signed", "verification_signed"
    )) or task.get("completion_checkbox_mark") != "[x]":
        raise P2T1ActivationError(f"{task_id} closed signoff is incomplete")
    refs = task.get("evidence_refs")
    if (not isinstance(refs, list) or not refs
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
            or len(set(refs)) != len(refs)):
        raise P2T1ActivationError(f"{task_id} has malformed or duplicated evidence refs")
    evidence = set(refs)
    if f"github:pr#{pr}" not in evidence:
        raise P2T1ActivationError(f"{task_id} lacks independent PR provenance")
    if not any(re.fullmatch(r"github-actions-run:[0-9]+", ref) for ref in evidence):
        raise P2T1ActivationError(f"{task_id} lacks an Actions acceptance run")
    if not {"skeleton/masterplan/closure.py", "tests/flgb/test_masterplan_closure.py"} <= evidence:
        raise P2T1ActivationError(f"{task_id} lacks canonical acceptance verifier refs")

    prefix = f"workflow:{workflow}@"
    workflow_heads = {
        ref[len(prefix):-len(":success")]
        for ref in evidence if ref.startswith(prefix) and ref.endswith(":success")
    }
    workflow_heads = {head for head in workflow_heads if re.fullmatch(r"[0-9a-f]{40}", head)}
    if not workflow_heads:
        raise P2T1ActivationError(f"{task_id} lacks pinned successful {workflow}")
    if require_matching_head:
        git_heads = {
            ref[len("git-head:"):] for ref in evidence
            if re.fullmatch(r"git-head:[0-9a-f]{40}", ref)
        }
        if not git_heads & workflow_heads:
            raise P2T1ActivationError(f"{task_id} workflow head does not match source evidence")
    elif not any(re.fullmatch(r"git:merge:[0-9a-f]{40}", ref) for ref in evidence):
        raise P2T1ActivationError(f"{task_id} lacks immutable merge evidence")


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

    tasks = {
        task.get("task_id"): task
        for task in backlog.get("tasks", [])
        if isinstance(task, dict) and task.get("task_id")
    }
    native = tasks.get("P2-NATIVE-01")
    if not isinstance(native, dict):
        raise P2T1ActivationError("P2-NATIVE-01 is missing")
    _check_task_state(
        "P2-NATIVE-01", native, pr="2332",
        workflow="P2 Profile-Gated Acceleration",
        require_matching_head=False,
    )

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
        _check_task_state(
            task_id, task, pr="2346", workflow="P2 Functional AI Acceptance",
        )

    # Perform precise activation/signoff checks before the comprehensive
    # canonical consistency pass; neither validator is bypassed.
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
