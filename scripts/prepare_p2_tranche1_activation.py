#!/usr/bin/env python3
"""Build a deterministic, non-mutating P2-T1 activation proposal.

This module never writes canonical P2 state. It validates the prepared T1 plan
and, only when every T0 activation dependency is landed_unpromoted, derives the
exact task/lane/partition changes an explicit follow-up activation PR must make.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = Path("machine/ai_p2_tranche1_plan.json")
P2_MAP = Path("machine/ai_p2_execution_map.json")
BACKLOG = Path("machine/ai_p2_task_backlog.json")
VALIDATOR = Path("scripts/check_p2_tranche1_plan.py")
P2_VALIDATOR = Path("scripts/check_p2_execution_map.py")


class P2Tranche1ActivationError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise P2Tranche1ActivationError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise P2Tranche1ActivationError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(value, dict):
        raise P2Tranche1ActivationError(f"{relative} must contain an object")
    return value


def _load_validator(root: Path):
    return _load_module(root, VALIDATOR, "check_p2_tranche1_plan")


def _load_module(root: Path, relative: Path, name: str):
    path = root / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise P2Tranche1ActivationError(f"cannot load validator: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _task_id(stream_id: str) -> str:
    mapping = {
        "P2-T1-DATA": "P2-T1-DATA-01",
        "P2-T1-SEC": "P2-T1-SEC-01",
        "P2-T1-INFER": "P2-T1-INFER-01",
        "P2-T1-RECOVERY": "P2-T1-RECOVERY-01",
        "P2-T1-FUNCTIONAL": "P2-T1-FUNCTIONAL-01",
    }
    try:
        return mapping[stream_id]
    except KeyError as exc:
        raise P2Tranche1ActivationError(
            f"unknown T1 workstream id: {stream_id}"
        ) from exc


def _lane_id(stream_id: str) -> str:
    mapping = {
        "P2-T1-DATA": "P2-T1-L0",
        "P2-T1-SEC": "P2-T1-L1",
        "P2-T1-INFER": "P2-T1-L2",
        "P2-T1-RECOVERY": "P2-T1-L3",
        "P2-T1-FUNCTIONAL": "P2-T1-L4",
    }
    return mapping[stream_id]


def _status_for(dependencies: list[str]) -> str:
    return "ready" if dependencies == ["P2-NATIVE-01"] else "blocked"


def build_activation_proposal(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    validator = _load_validator(root)
    try:
        plan_result = validator.validate(root)
    except Exception as exc:
        raise P2Tranche1ActivationError(
            f"prepared T1 plan validation failed: {exc}"
        ) from exc

    if not plan_result.get("activation_ready"):
        blockers = list(plan_result.get("activation_blockers", []))
        raise P2Tranche1ActivationError(
            "T1 activation fence is not satisfied; blockers=" + ",".join(blockers)
        )

    plan = _load(root, PLAN)
    p2 = _load(root, P2_MAP)
    backlog = _load(root, BACKLOG)

    selected = list(plan["selection"]["selected_volume_refs"])
    selected_set = set(selected)
    current_scheduled = list(p2["first_tranche"]["scheduled_volume_refs"])
    current_queued = list(p2["first_tranche"]["queued_volume_refs"])

    if selected_set - set(current_queued):
        raise P2Tranche1ActivationError("selected T1 scope is not entirely queued")
    if selected_set & set(current_scheduled):
        raise P2Tranche1ActivationError("selected T1 scope overlaps scheduled T0 scope")

    proposed_scheduled = current_scheduled + selected
    proposed_queued = [ref for ref in current_queued if ref not in selected_set]
    source = list(p2["source_scope"]["volume_refs"])
    if set(proposed_scheduled) | set(proposed_queued) != set(source):
        raise P2Tranche1ActivationError("activation proposal loses P2 source scope")
    if set(proposed_scheduled) & set(proposed_queued):
        raise P2Tranche1ActivationError("activation proposal overlaps scheduled/queued scope")
    if len(proposed_scheduled) != len(set(proposed_scheduled)):
        raise P2Tranche1ActivationError("activation proposal duplicates scheduled volumes")

    evidence_by_ref = {
        item["volume_ref"]: item
        for item in plan["volume_selection_evidence"]
    }
    stream_to_task = {
        stream["id"]: _task_id(stream["id"])
        for stream in plan["workstreams"]
    }

    proposed_tasks: list[dict[str, Any]] = []
    proposed_lanes: list[dict[str, Any]] = []
    owned: list[str] = []

    existing_lanes = p2.get("lanes", [])
    if not isinstance(existing_lanes, list) or not existing_lanes:
        raise P2Tranche1ActivationError("canonical P2 lane set must be non-empty")
    existing_lane_ids = {
        lane.get("id")
        for lane in existing_lanes
        if isinstance(lane, dict)
    }
    existing_sequences = [
        lane.get("sequence")
        for lane in existing_lanes
        if isinstance(lane, dict)
    ]
    if (
        len(existing_lane_ids) != len(existing_lanes)
        or any(not isinstance(value, int) for value in existing_sequences)
        or len(set(existing_sequences)) != len(existing_sequences)
    ):
        raise P2Tranche1ActivationError(
            "canonical P2 lanes must have unique ids and integer sequences"
        )
    next_sequence = max(existing_sequences) + 1

    for offset, stream in enumerate(plan["workstreams"]):
        stream_id = stream["id"]
        task_id = stream_to_task[stream_id]
        stream_dependencies = [
            stream_to_task[dep]
            for dep in stream.get("depends_on", [])
        ]
        dependencies = (
            ["P2-NATIVE-01"]
            if not stream_dependencies
            else stream_dependencies
        )
        refs = list(stream["volume_refs"])
        owned.extend(refs)

        obligations = [
            dict(evidence_by_ref[ref]["masterplan_obligation"])
            for ref in refs
        ]

        proposed_tasks.append(
            {
                "task_id": task_id,
                "lane_id": _lane_id(stream_id),
                "status": _status_for(dependencies),
                "title": stream["name"],
                "depends_on": dependencies,
                "primary_volume_refs": refs,
                "objective": stream["objective"],
                "acceptance": [
                    "All inherited masterplan gaps remain explicit until evidence closes them.",
                    "Focused negative/recovery evidence exists for every implemented boundary.",
                    "No task may self-promote maturity, completion, or verification sign-off.",
                ],
                "priority": "P2",
                "accountability_required": True,
                "completion_checkbox": False,
                "completion_checkbox_mark": "[ ]",
                "implementation_signed": False,
                "verification_signed": False,
                "evidence_refs": [
                    "plan:machine/ai_p2_tranche1_plan.json",
                    "dependency:P2-T0:all-landed-unpromoted",
                ],
                "masterplan_obligations": obligations,
            }
        )
        lane_id = _lane_id(stream_id)
        if lane_id in existing_lane_ids:
            raise P2Tranche1ActivationError(
                f"T1 lane id collides with existing lane: {lane_id}"
            )
        lane_dependencies = [
            _lane_id(dep)
            for dep in stream.get("depends_on", [])
        ]
        if not lane_dependencies:
            lane_dependencies = ["P2-L6"]
        proposed_lanes.append(
            {
                "id": lane_id,
                "name": stream["name"],
                "sequence": next_sequence + offset,
                "depends_on": lane_dependencies,
            }
        )

    if set(owned) != selected_set:
        raise P2Tranche1ActivationError(
            "workstream task ownership must equal selected_volume_refs"
        )
    if len(owned) != len(set(owned)):
        raise P2Tranche1ActivationError("T1 task ownership contains duplicate volumes")

    existing_ids = {
        task.get("task_id")
        for task in backlog.get("tasks", [])
        if isinstance(task, dict)
    }
    collisions = sorted(
        task["task_id"] for task in proposed_tasks
        if task["task_id"] in existing_ids
    )
    if collisions:
        raise P2Tranche1ActivationError(
            f"T1 task ids collide with existing backlog: {collisions}"
        )

    return {
        "schema_version": "skeleton.p2.tranche_activation_proposal.v1",
        "status": "proposal_only",
        "source_plan": PLAN.as_posix(),
        "activation_fence": {
            "required_status": "landed_unpromoted",
            "t0_task_ids": list(plan["activation"]["required_first_tranche_task_ids"]),
            "satisfied": True,
        },
        "partition": {
            "source_volume_count": len(source),
            "scheduled_before": len(current_scheduled),
            "scheduled_after": len(proposed_scheduled),
            "queued_before": len(current_queued),
            "queued_after": len(proposed_queued),
            "activated_volume_count": len(selected),
            "activated_volume_refs": selected,
            "scheduled_volume_refs": proposed_scheduled,
            "queued_volume_refs": proposed_queued,
        },
        "new_lanes": proposed_lanes,
        "new_tasks": proposed_tasks,
        "non_authority": [
            "This proposal does not mutate machine/ai_p2_execution_map.json.",
            "This proposal does not mutate machine/ai_p2_task_backlog.json.",
            "A separate reviewed activation change must apply and validate the proposal.",
            "No proposed task claims completion, maturity promotion, or sign-off.",
        ],
    }


def validate_proposal_against_canonical_map(
    root: Path,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Apply the proposal only in a disposable fixture and run canonical P2 validation."""
    root = root.resolve()
    required = (
        "machine/ai_master_plan.json",
        "machine/ai_master_build_sequence.json",
        "machine/ai_p1_execution_map.json",
        "machine/ai_p2_execution_map.json",
        "machine/ai_p2_task_backlog.json",
        "scripts/check_p2_execution_map.py",
    )
    with tempfile.TemporaryDirectory(prefix="p2-t1-canonical-") as raw_temp:
        temp = Path(raw_temp)
        for relative in required:
            src = root / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        map_path = temp / P2_MAP
        p2 = json.loads(map_path.read_text(encoding="utf-8"))
        partition = proposal["partition"]
        p2["first_tranche"]["scheduled_volume_refs"] = list(
            partition["scheduled_volume_refs"]
        )
        p2["first_tranche"]["scheduled_volume_count"] = int(
            partition["scheduled_after"]
        )
        p2["first_tranche"]["queued_volume_refs"] = list(
            partition["queued_volume_refs"]
        )
        p2["first_tranche"]["queued_volume_count"] = int(
            partition["queued_after"]
        )
        p2["lanes"].extend(proposal["new_lanes"])
        map_path.write_text(json.dumps(p2, indent=2) + "\n", encoding="utf-8")

        backlog_path = temp / BACKLOG
        backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
        backlog["tasks"].extend(proposal["new_tasks"])
        tasks = backlog["tasks"]
        backlog["summary"] = {
            "task_count": len(tasks),
            "in_progress_count": sum(
                task.get("status") == "in_progress" for task in tasks
            ),
            "ready_count": sum(task.get("status") == "ready" for task in tasks),
            "blocked_count": sum(
                task.get("status") == "blocked" for task in tasks
            ),
            "landed_unpromoted_count": sum(
                task.get("status") == "landed_unpromoted" for task in tasks
            ),
            "scheduled_volume_count": int(partition["scheduled_after"]),
            "queued_volume_count": int(partition["queued_after"]),
            "source_volume_count": int(partition["source_volume_count"]),
        }
        backlog_path.write_text(
            json.dumps(backlog, indent=2) + "\n",
            encoding="utf-8",
        )

        validator = _load_module(
            temp,
            P2_VALIDATOR,
            "check_p2_execution_map_activation_fixture",
        )
        try:
            result = validator.validate(temp)
        except Exception as exc:
            raise P2Tranche1ActivationError(
                f"canonical P2 validator rejected activation proposal: {exc}"
            ) from exc
        if result.get("status") != "valid":
            raise P2Tranche1ActivationError(
                f"canonical P2 validator returned unexpected result: {result!r}"
            )
        return dict(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        proposal = build_activation_proposal(Path(args.repo_root))
    except P2Tranche1ActivationError as exc:
        print(f"P2 tranche 1 activation proposal: BLOCKED: {exc}", file=sys.stderr)
        return 2
    canonical = validate_proposal_against_canonical_map(Path(args.repo_root), proposal)
    proposal["canonical_validation"] = canonical
    if args.json:
        print(json.dumps(proposal, sort_keys=True))
    else:
        partition = proposal["partition"]
        print(
            "P2 tranche 1 activation proposal: READY "
            f"({partition['activated_volume_count']} activate, "
            f"{partition['scheduled_after']} scheduled, "
            f"{partition['queued_after']} queued)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
