#!/usr/bin/env python3
"""Validate the canonical P1-PROM-01 terminal evidence policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.p1_terminal_evidence import (
    P1_TERMINAL_EVIDENCE_ACCOUNTABILITY_ID,
    P1_TERMINAL_EVIDENCE_TASK_ID,
    P1_TERMINAL_REQUIRED_TASKS,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("machine/p1_terminal_evidence_policy.json")
BACKLOG_PATH = Path("machine/ai_p1_task_backlog.json")
MAP_PATH = Path("machine/ai_p1_execution_map.json")


class TerminalPolicyError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalPolicyError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise TerminalPolicyError(f"{path} must contain an object")
    return value


def _required_primary_volumes(execution_map: dict[str, Any]) -> tuple[str, ...]:
    lanes = execution_map.get("lanes")
    if not isinstance(lanes, list):
        raise TerminalPolicyError("execution map lanes must be a list")
    values: set[str] = set()
    for lane in lanes:
        if not isinstance(lane, dict):
            raise TerminalPolicyError("lane entries must be objects")
        refs = lane.get("primary_volume_refs")
        if not isinstance(refs, list) or any(
            not isinstance(item, str) or not item for item in refs
        ):
            raise TerminalPolicyError(
                f"{lane.get('id', '?')}: primary_volume_refs invalid"
            )
        overlap = values.intersection(refs)
        if overlap:
            raise TerminalPolicyError(
                "primary volume ownership is duplicated: "
                + ",".join(sorted(overlap))
            )
        values.update(refs)
    if not values:
        raise TerminalPolicyError("P1 primary volume scope is empty")
    return tuple(sorted(values))


def validate_repository(root: Path = ROOT) -> dict[str, Any]:
    policy = _load(root / POLICY_PATH)
    backlog = _load(root / BACKLOG_PATH)
    execution_map = _load(root / MAP_PATH)

    allowed = {
        "schema_version",
        "task_id",
        "accountability_ref",
        "authority",
        "dependency_authority",
        "primary_volume_authority",
        "promotion_authority",
        "signed_promotion",
        "allow_explicit_maturity_blockers",
        "require_exact_head",
        "require_complete_primary_volume_coverage",
        "required_receipts",
    }
    unknown = set(policy) - allowed
    if unknown:
        raise TerminalPolicyError(
            f"unknown terminal policy fields: {sorted(unknown)}"
        )
    if policy.get("schema_version") != 1:
        raise TerminalPolicyError("schema_version must equal 1")
    if policy.get("task_id") != P1_TERMINAL_EVIDENCE_TASK_ID:
        raise TerminalPolicyError("task_id drift")
    if (
        policy.get("accountability_ref")
        != P1_TERMINAL_EVIDENCE_ACCOUNTABILITY_ID
    ):
        raise TerminalPolicyError("accountability_ref drift")
    if policy.get("authority") != str(POLICY_PATH):
        raise TerminalPolicyError("authority path drift")
    if policy.get("dependency_authority") != str(BACKLOG_PATH):
        raise TerminalPolicyError("dependency authority drift")
    if policy.get("primary_volume_authority") != str(MAP_PATH):
        raise TerminalPolicyError("primary volume authority drift")
    for field in (
        "promotion_authority",
        "signed_promotion",
    ):
        if policy.get(field) is not False:
            raise TerminalPolicyError(
                f"{field} must remain false for PROM-01"
            )
    for field in (
        "allow_explicit_maturity_blockers",
        "require_exact_head",
        "require_complete_primary_volume_coverage",
    ):
        if policy.get(field) is not True:
            raise TerminalPolicyError(f"{field} must remain true")

    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise TerminalPolicyError("backlog tasks must be a list")
    prom = next(
        (
            row for row in tasks
            if isinstance(row, dict)
            and row.get("task_id") == P1_TERMINAL_EVIDENCE_TASK_ID
        ),
        None,
    )
    if prom is None:
        raise TerminalPolicyError("PROM-01 task missing from backlog")
    dependencies = prom.get("depends_on")
    if not isinstance(dependencies, list) or any(
        not isinstance(item, str) or not item for item in dependencies
    ):
        raise TerminalPolicyError("PROM-01 dependencies malformed")
    expected_tasks = tuple(task for task, _ in P1_TERMINAL_REQUIRED_TASKS)
    if tuple(dependencies) != expected_tasks:
        raise TerminalPolicyError(
            "PROM-01 dependency order/identity drift"
        )

    rows = policy.get("required_receipts")
    if not isinstance(rows, list):
        raise TerminalPolicyError("required_receipts must be a list")
    observed: list[tuple[str, str]] = []
    all_test_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise TerminalPolicyError(
                "required_receipts entries must be objects"
            )
        if set(row) != {
            "task_id",
            "accountability_id",
            "test_paths",
        }:
            raise TerminalPolicyError(
                "required receipt fields drift"
            )
        task = row.get("task_id")
        accountability = row.get("accountability_id")
        paths = row.get("test_paths")
        if not isinstance(task, str) or not task:
            raise TerminalPolicyError("receipt task_id invalid")
        if not isinstance(accountability, str) or not accountability:
            raise TerminalPolicyError(
                f"{task}: accountability_id invalid"
            )
        if not isinstance(paths, list) or not paths or any(
            not isinstance(item, str) or not item for item in paths
        ):
            raise TerminalPolicyError(f"{task}: test_paths invalid")
        for raw in paths:
            path = Path(raw)
            if path.is_absolute() or ".." in path.parts:
                raise TerminalPolicyError(
                    f"{task}: unsafe test path {raw}"
                )
            if not (root / path).is_file():
                raise TerminalPolicyError(
                    f"{task}: missing test path {raw}"
                )
            all_test_paths.add(raw)
        observed.append((task, accountability))

    if tuple(observed) != P1_TERMINAL_REQUIRED_TASKS:
        raise TerminalPolicyError(
            "required terminal receipt identity drift"
        )

    primary_volumes = _required_primary_volumes(execution_map)
    return {
        "schema_version": 1,
        "task_id": P1_TERMINAL_EVIDENCE_TASK_ID,
        "accountability_ref": P1_TERMINAL_EVIDENCE_ACCOUNTABILITY_ID,
        "required_receipt_count": len(observed),
        "primary_volume_count": len(primary_volumes),
        "test_path_count": len(all_test_paths),
        "promotion_authority": False,
        "signed_promotion": False,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = validate_repository(ROOT)
    except TerminalPolicyError as exc:
        print(
            f"P1 terminal evidence policy: rejected: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.print_summary:
        print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "P1 terminal evidence policy: OK "
        f"({summary['required_receipt_count']} receipts, "
        f"{summary['primary_volume_count']} primary volumes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
