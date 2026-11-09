#!/usr/bin/env python3
"""Validate the canonical P1-PROM-02 failure-journey policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("machine/p1_terminal_failure_journeys.json")
MAP_PATH = Path("machine/ai_p1_execution_map.json")
BACKLOG_PATH = Path("machine/ai_p1_task_backlog.json")
PROM01_POLICY_PATH = Path("machine/p1_terminal_evidence_policy.json")
EXPECTED_TASK = "P1-PROM-02"
EXPECTED_ACCOUNTABILITY = "ACC-P1-PROM-02"
EXPECTED_DEPENDENCIES = ["P1-PROM-01"]
EXPECTED_CLASSES = (
    "adversarial",
    "clean-machine",
    "partition",
    "provider-failover",
    "restore",
    "rollback",
    "saturation",
    "stale-evidence",
)


class TerminalJourneyPolicyError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalJourneyPolicyError(f"cannot read {path}") from exc


def _strict_keys(row: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise TerminalJourneyPolicyError(
            f"{label}: unknown fields {sorted(unknown)}"
        )


def validate_repository(
    root: Path = ROOT,
    *,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    policy = _load(root / policy_path)
    execution_map = _load(root / MAP_PATH)
    backlog = _load(root / BACKLOG_PATH)
    prom01 = _load(root / PROM01_POLICY_PATH)

    if not isinstance(policy, dict):
        raise TerminalJourneyPolicyError("policy root must be object")
    _strict_keys(
        policy,
        {
            "schema_version",
            "task_id",
            "accountability_ref",
            "authority",
            "execution_map_authority",
            "task_backlog_authority",
            "prom01_policy_authority",
            "promotion_authority",
            "signed_promotion",
            "require_exact_head",
            "require_independent_verification",
            "journey_classes",
            "failure_families",
        },
        "policy",
    )
    if policy.get("schema_version") != 1:
        raise TerminalJourneyPolicyError("schema_version must equal 1")
    if policy.get("task_id") != EXPECTED_TASK:
        raise TerminalJourneyPolicyError("task_id drift")
    if policy.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise TerminalJourneyPolicyError("accountability_ref drift")
    if policy.get("authority") != str(POLICY_PATH):
        raise TerminalJourneyPolicyError("authority path drift")
    if policy.get("execution_map_authority") != str(MAP_PATH):
        raise TerminalJourneyPolicyError("execution map authority drift")
    if policy.get("task_backlog_authority") != str(BACKLOG_PATH):
        raise TerminalJourneyPolicyError("task backlog authority drift")
    if policy.get("prom01_policy_authority") != str(PROM01_POLICY_PATH):
        raise TerminalJourneyPolicyError("PROM-01 policy authority drift")
    if policy.get("promotion_authority") is not False:
        raise TerminalJourneyPolicyError(
            "promotion_authority must remain false"
        )
    if policy.get("signed_promotion") is not False:
        raise TerminalJourneyPolicyError("signed_promotion must remain false")
    if policy.get("require_exact_head") is not True:
        raise TerminalJourneyPolicyError("exact-head verification required")
    if policy.get("require_independent_verification") is not True:
        raise TerminalJourneyPolicyError(
            "independent verification required"
        )

    if not isinstance(execution_map, dict):
        raise TerminalJourneyPolicyError("execution map root must be object")
    acceptance = execution_map.get("acceptance_program")
    if not isinstance(acceptance, dict):
        raise TerminalJourneyPolicyError(
            "execution map acceptance_program missing"
        )
    canonical_families = acceptance.get("required_failure_families")
    if not isinstance(canonical_families, list) or any(
        not isinstance(item, str) or not item
        for item in canonical_families
    ):
        raise TerminalJourneyPolicyError(
            "required_failure_families must be string list"
        )

    rows = policy.get("failure_families")
    if not isinstance(rows, list) or not rows:
        raise TerminalJourneyPolicyError(
            "failure_families must be non-empty list"
        )
    seen: set[str] = set()
    all_test_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise TerminalJourneyPolicyError(
                "failure family entries must be objects"
            )
        _strict_keys(row, {"family", "test_paths"}, "failure family")
        family = row.get("family")
        paths = row.get("test_paths")
        if not isinstance(family, str) or not family:
            raise TerminalJourneyPolicyError(
                "failure family name must be non-empty"
            )
        if family in seen:
            raise TerminalJourneyPolicyError(
                f"duplicate failure family: {family}"
            )
        seen.add(family)
        if not isinstance(paths, list) or not paths or any(
            not isinstance(item, str) or not item for item in paths
        ):
            raise TerminalJourneyPolicyError(
                f"{family}: test_paths must be non-empty string list"
            )
        for raw in paths:
            if not (root / raw).is_file():
                raise TerminalJourneyPolicyError(
                    f"{family}: missing test path {raw}"
                )
            all_test_paths.add(raw)

    if [row["family"] for row in rows] != canonical_families:
        raise TerminalJourneyPolicyError(
            "failure family order/identity drift from execution map"
        )

    classes = policy.get("journey_classes")
    if not isinstance(classes, dict):
        raise TerminalJourneyPolicyError(
            "journey_classes must be an object"
        )
    if tuple(sorted(classes)) != EXPECTED_CLASSES:
        raise TerminalJourneyPolicyError(
            "terminal journey class identity drift"
        )
    for journey_class, families in classes.items():
        if not isinstance(families, list) or not families or any(
            not isinstance(item, str) or not item for item in families
        ):
            raise TerminalJourneyPolicyError(
                f"{journey_class}: family coverage must be non-empty list"
            )
        unknown = sorted(set(families) - seen)
        if unknown:
            raise TerminalJourneyPolicyError(
                f"{journey_class}: unknown families {unknown}"
            )

    tasks = backlog.get("tasks") if isinstance(backlog, dict) else None
    if not isinstance(tasks, list):
        raise TerminalJourneyPolicyError("task backlog tasks missing")
    task = next(
        (
            row
            for row in tasks
            if isinstance(row, dict)
            and row.get("task_id") == EXPECTED_TASK
        ),
        None,
    )
    if task is None:
        raise TerminalJourneyPolicyError("PROM-02 task missing")
    if task.get("depends_on") != EXPECTED_DEPENDENCIES:
        raise TerminalJourneyPolicyError(
            "PROM-02 dependency identity drift"
        )
    if task.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise TerminalJourneyPolicyError(
            "PROM-02 task accountability drift"
        )
    if prom01.get("task_id") != "P1-PROM-01":
        raise TerminalJourneyPolicyError("PROM-01 policy task drift")
    if prom01.get("promotion_authority") is not False:
        raise TerminalJourneyPolicyError(
            "PROM-01 unexpectedly carries promotion authority"
        )

    return {
        "schema_version": 1,
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "failure_family_count": len(rows),
        "journey_class_count": len(classes),
        "test_path_count": len(all_test_paths),
        "promotion_authority": False,
        "signed_promotion": False,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = validate_repository(ROOT, policy_path=args.policy)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except TerminalJourneyPolicyError as exc:
        print(f"P1 terminal failure journeys: rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
