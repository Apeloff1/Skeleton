#!/usr/bin/env python3
"""Build unsigned P1 volume accountability review candidates.

This report is advisory only. It never mutates the accountability ledger,
masterplan, task backlog, or any signoff. Identity-bound signing must still
flow through scripts/ai_accountability.py with distinct implementation and
verification actors.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_p1_maturity import ROOT, reconcile_repository


BACKLOG = ROOT / "machine/ai_p1_task_backlog.json"

_ACCOUNTABILITY_MARKERS = (
    "implementation accountability is unsigned",
    "independent verification is unsigned",
    "accountability status is below ",
    "accountability evidence is not materialized",
)
_GAP_MARKER = "unresolved volume gaps remain"


class CandidateError(RuntimeError):
    """Accountability candidate inputs are inconsistent."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise CandidateError(f"{path} must contain an object")
    return value


def _mapped_tasks(backlog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise CandidateError("P1 task backlog tasks must be a list")

    out: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise CandidateError("P1 task entries must be objects")
        task_id = task.get("task_id")
        volume_refs = task.get("volume_refs")
        if not isinstance(task_id, str) or not task_id:
            raise CandidateError("P1 task_id is required")
        if not isinstance(volume_refs, list):
            raise CandidateError(f"{task_id}: volume_refs must be a list")
        for raw_key in volume_refs:
            out.setdefault(str(raw_key), []).append(task)
    return out


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _is_accountability_blocker(blocker: str) -> bool:
    return any(marker in blocker for marker in _ACCOUNTABILITY_MARKERS)


def _evaluation(row: dict[str, Any], state: str) -> dict[str, Any]:
    return next(
        item
        for item in row["evaluations"]
        if item["state"] == state
    )


def build_candidates(root: Path = ROOT) -> dict[str, Any]:
    report = reconcile_repository(root)
    backlog = _load(root / "machine/ai_p1_task_backlog.json")
    tasks_by_volume = _mapped_tasks(backlog)

    rows: list[dict[str, Any]] = []
    for row in report["records"]:
        volume_key = row["volume_key"]
        tasks = tasks_by_volume.get(volume_key, [])
        if not tasks:
            raise CandidateError(f"{volume_key}: no mapped P1 task")

        implemented = _evaluation(row, "implemented")
        verified = _evaluation(row, "verified")
        target = _evaluation(row, row["target_floor"])

        implementation_non_governance = [
            blocker
            for blocker in implemented["blockers"]
            if not _is_accountability_blocker(blocker)
        ]
        verification_non_governance = [
            blocker
            for blocker in verified["blockers"]
            if not _is_accountability_blocker(blocker)
        ]
        target_non_governance = [
            blocker
            for blocker in target["blockers"]
            if not _is_accountability_blocker(blocker)
        ]

        evidence_refs = _dedupe(
            [
                str(reference)
                for task in tasks
                for reference in task.get("evidence_refs", [])
                if isinstance(reference, str)
                and reference
                and not reference.startswith("planned:")
            ]
        )
        if not evidence_refs:
            raise CandidateError(
                f"{volume_key}: mapped tasks have no materialized evidence"
            )

        actions: list[str] = []
        if row["implementation_signed"] is False:
            actions.append("implementation_signoff")
        if row["verification_signed"] is False:
            actions.append("independent_verification_signoff")
        if any(_GAP_MARKER in blocker for blocker in target["blockers"]):
            actions.append("gap_closure_or_governed_disposition")
        if row["target_floor_eligible"] is False:
            actions.append("target_floor_reconciliation")

        rows.append(
            {
                "volume_key": volume_key,
                "accountability_id": row["accountability_id"],
                "lane_id": row["lane_id"],
                "target_floor": row["target_floor"],
                "current_status": row["current_status"],
                "current_implementation_status": (
                    row["current_implementation_status"]
                ),
                "accountability_status": row["accountability_status"],
                "implementation_signed": row["implementation_signed"],
                "verification_signed": row["verification_signed"],
                "mapped_task_ids": [str(task["task_id"]) for task in tasks],
                "evidence_refs": evidence_refs,
                "implementation_review_ready": (
                    not implementation_non_governance
                ),
                "verification_evidence_ready_after_implementation": (
                    not verification_non_governance
                ),
                "target_floor_eligible": row["target_floor_eligible"],
                "promotion_candidate": row["promotion_candidate"],
                "implemented_non_governance_blockers": (
                    implementation_non_governance
                ),
                "verified_non_governance_blockers": (
                    verification_non_governance
                ),
                "target_non_governance_blockers": target_non_governance,
                "remaining_target_blockers": list(target["blockers"]),
                "required_review_actions": actions,
            }
        )

    implementation_ready = sum(
        1 for row in rows if row["implementation_review_ready"]
    )
    verification_ready = sum(
        1
        for row in rows
        if row["verification_evidence_ready_after_implementation"]
    )
    gap_blocked = sum(
        1
        for row in rows
        if "gap_closure_or_governed_disposition"
        in row["required_review_actions"]
    )
    target_ready = sum(
        1 for row in rows if row["target_floor_eligible"]
    )

    return {
        "schema_version": 1,
        "engine": "p1-volume-accountability-candidates-v1",
        "non_authoritative": True,
        "mutates_accountability": False,
        "creates_signatures": False,
        "requires_distinct_verifier_identity": True,
        "volume_count": len(rows),
        "implementation_review_ready_count": implementation_ready,
        "verification_evidence_ready_count": verification_ready,
        "gap_blocked_count": gap_blocked,
        "target_floor_eligible_count": target_ready,
        "records": rows,
    }


def _canonical_text(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional output path for the unsigned candidate report.",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
    )
    args = parser.parse_args(argv)

    try:
        report = build_candidates(ROOT)
    except CandidateError as exc:
        print(
            f"P1 accountability candidates: rejected: {exc}",
            file=__import__("sys").stderr,
        )
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_canonical_text(report), encoding="utf-8")

    if args.print_summary:
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "volume_count",
                        "implementation_review_ready_count",
                        "verification_evidence_ready_count",
                        "gap_blocked_count",
                        "target_floor_eligible_count",
                    )
                },
                indent=2,
                sort_keys=True,
            )
        )

    print(
        "P1 accountability candidates: OK "
        f"({report['volume_count']} volumes; "
        f"{report['implementation_review_ready_count']} implementation-review "
        "ready; "
        f"{report['verification_evidence_ready_count']} verification-evidence "
        "ready; "
        f"{report['gap_blocked_count']} gap-blocked; "
        f"{report['target_floor_eligible_count']} at lane floor)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
