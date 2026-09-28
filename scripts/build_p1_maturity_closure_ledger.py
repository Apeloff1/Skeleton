#!/usr/bin/env python3
"""Build a deterministic, non-authoritative P1 maturity closure ledger.

The ledger converts the non-mutating maturity reconciliation report into an
action inventory. It never signs accountability, advances maturity, closes
gaps, checks completion boxes, or mutates any canonical source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from reconcile_p1_maturity import ReconciliationError, reconcile_repository


ROOT = Path(__file__).resolve().parents[1]
BACKLOG = Path("machine/ai_p1_task_backlog.json")
EXECUTION_MAP = Path("machine/ai_p1_execution_map.json")
LEDGER = Path("machine/p1_maturity_closure_ledger.json")

MATURITY_ORDER = (
    "specified",
    "scaffolded",
    "implemented",
    "integrated",
    "verified",
    "hardened",
    "production",
)
MATURITY_INDEX = {state: index for index, state in enumerate(MATURITY_ORDER)}

ACTION_IMPLEMENTATION_SIGNOFF = "implementation_signoff"
ACTION_VERIFICATION_SIGNOFF = "independent_verification_signoff"
ACTION_ACCOUNTABILITY_STATUS = "accountability_maturity_status"
ACTION_ACCOUNTABILITY_EVIDENCE = "accountability_evidence"
ACTION_GAP_CLOSURE = "resolve_volume_gaps"

ALLOWED_ACTIONS = (
    ACTION_IMPLEMENTATION_SIGNOFF,
    ACTION_VERIFICATION_SIGNOFF,
    ACTION_ACCOUNTABILITY_STATUS,
    ACTION_ACCOUNTABILITY_EVIDENCE,
    ACTION_GAP_CLOSURE,
)

_METADATA_BLOCKER_MARKERS = (
    "must contain materialized references",
    "contains unresolved repository references",
)


class ClosureLedgerError(RuntimeError):
    """Closure-ledger inputs are malformed or violate fail-closed policy."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureLedgerError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise ClosureLedgerError(f"{path} must contain an object")
    return payload


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _primary_owners(execution_map: dict[str, Any]) -> dict[str, dict[str, str]]:
    lanes = execution_map.get("lanes")
    if not isinstance(lanes, list):
        raise ClosureLedgerError("P1 execution map lanes must be a list")

    owners: dict[str, dict[str, str]] = {}
    for lane in lanes:
        if not isinstance(lane, dict):
            raise ClosureLedgerError("P1 lane entries must be objects")
        lane_id = lane.get("id")
        target = lane.get("target_maturity")
        refs = lane.get("primary_volume_refs")
        if not isinstance(lane_id, str) or not lane_id:
            raise ClosureLedgerError("P1 lane id is required")
        if target not in MATURITY_INDEX:
            raise ClosureLedgerError(f"{lane_id}: invalid target maturity")
        if not isinstance(refs, list):
            raise ClosureLedgerError(
                f"{lane_id}: primary_volume_refs must be a list"
            )
        for raw_ref in refs:
            ref = str(raw_ref)
            if ref in owners:
                raise ClosureLedgerError(
                    f"duplicate primary volume ownership: {ref}"
                )
            owners[ref] = {
                "lane_id": lane_id,
                "target_maturity": str(target),
            }
    return owners


def _tasks_by_volume(backlog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise ClosureLedgerError("P1 task backlog tasks must be a list")

    by_volume: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise ClosureLedgerError("P1 task entries must be objects")
        task_id = task.get("task_id")
        refs = task.get("volume_refs")
        if not isinstance(task_id, str) or not task_id:
            raise ClosureLedgerError("P1 task_id is required")
        if not isinstance(refs, list):
            raise ClosureLedgerError(
                f"{task_id}: volume_refs must be a list"
            )
        for raw_ref in refs:
            by_volume.setdefault(str(raw_ref), []).append(task)
    return by_volume


def _target_evaluation(row: dict[str, Any]) -> dict[str, Any]:
    target = row["target_floor"]
    matches = [
        item
        for item in row["evaluations"]
        if item["state"] == target
    ]
    if len(matches) != 1:
        raise ClosureLedgerError(
            f"{row['volume_key']}: target evaluation is missing or duplicated"
        )
    return matches[0]


def _required_actions(
    row: dict[str, Any],
    target_blockers: list[str],
) -> list[str]:
    target = str(row["target_floor"])
    target_rank = MATURITY_INDEX[target]
    actions: list[str] = []

    if target_rank >= MATURITY_INDEX["implemented"]:
        if row["implementation_signed"] is not True:
            actions.append(ACTION_IMPLEMENTATION_SIGNOFF)

        accountability_state = row.get("accountability_maturity_status")
        accountability_rank = (
            MATURITY_INDEX.get(str(accountability_state), -1)
            if accountability_state is not None
            else -1
        )
        if accountability_rank < target_rank:
            actions.append(ACTION_ACCOUNTABILITY_STATUS)

    if (
        target_rank >= MATURITY_INDEX["verified"]
        and row["verification_signed"] is not True
    ):
        actions.append(ACTION_VERIFICATION_SIGNOFF)

    if target_rank >= MATURITY_INDEX["hardened"]:
        if any(
            "accountability evidence is not materialized" in blocker
            for blocker in target_blockers
        ):
            actions.append(ACTION_ACCOUNTABILITY_EVIDENCE)
        if any(
            "unresolved volume gaps remain" in blocker
            for blocker in target_blockers
        ):
            actions.append(ACTION_GAP_CLOSURE)

    return [
        action
        for action in ALLOWED_ACTIONS
        if action in actions
    ]


def build_ledger(root: Path = ROOT) -> dict[str, Any]:
    try:
        reconciliation = reconcile_repository(root)
    except ReconciliationError as exc:
        raise ClosureLedgerError(str(exc)) from exc

    backlog = _load(root / BACKLOG)
    execution_map = _load(root / EXECUTION_MAP)
    owners = _primary_owners(execution_map)
    tasks_by_volume = _tasks_by_volume(backlog)

    records: list[dict[str, Any]] = []
    action_counts = {action: 0 for action in ALLOWED_ACTIONS}
    lane_counts: dict[str, dict[str, int]] = {}

    reconciliation_by_key = {
        str(row["volume_key"]): row
        for row in reconciliation["records"]
    }
    if set(reconciliation_by_key) != set(owners):
        raise ClosureLedgerError(
            "maturity reconciliation and P1 primary ownership differ"
        )

    for key in sorted(owners):
        row = reconciliation_by_key[key]
        owner = owners[key]
        evaluation = _target_evaluation(row)
        blockers = list(evaluation["blockers"])

        metadata_blockers = [
            blocker
            for blocker in blockers
            if any(
                marker in blocker
                for marker in _METADATA_BLOCKER_MARKERS
            )
        ]
        if metadata_blockers:
            raise ClosureLedgerError(
                f"{key}: metadata blockers remain: {metadata_blockers}"
            )

        tasks = tasks_by_volume.get(key, [])
        if not tasks:
            raise ClosureLedgerError(f"{key}: no mapped P1 tasks")

        required_actions = _required_actions(row, blockers)
        eligible = row["target_floor_eligible"] is True

        if eligible and required_actions:
            raise ClosureLedgerError(
                f"{key}: eligible volume still has closure actions"
            )
        if not eligible and not required_actions:
            raise ClosureLedgerError(
                f"{key}: blocked volume has no classified closure action"
            )

        lane_id = owner["lane_id"]
        lane_summary = lane_counts.setdefault(
            lane_id,
            {
                "primary_volume_count": 0,
                "target_floor_eligible_count": 0,
                "blocked_volume_count": 0,
            },
        )
        lane_summary["primary_volume_count"] += 1
        if eligible:
            lane_summary["target_floor_eligible_count"] += 1
        else:
            lane_summary["blocked_volume_count"] += 1

        for action in required_actions:
            action_counts[action] += 1

        task_ids = sorted(
            str(task["task_id"])
            for task in tasks
        )
        evidence_refs = sorted(
            {
                str(reference)
                for task in tasks
                for reference in task.get("evidence_refs", [])
                if isinstance(reference, str)
                and reference
                and not reference.startswith("planned:")
            }
        )
        if not evidence_refs:
            raise ClosureLedgerError(
                f"{key}: mapped tasks have no materialized evidence"
            )

        records.append(
            {
                "volume_key": key,
                "lane_id": lane_id,
                "target_floor": owner["target_maturity"],
                "current_status": row["current_status"],
                "current_implementation_status": row[
                    "current_implementation_status"
                ],
                "accountability_id": row["accountability_id"],
                "accountability_status": row["accountability_status"],
                "accountability_maturity_status": row[
                    "accountability_maturity_status"
                ],
                "implementation_signed": row["implementation_signed"],
                "verification_signed": row["verification_signed"],
                "target_floor_eligible": eligible,
                "target_floor_blockers": blockers,
                "required_actions": required_actions,
                "mapped_task_ids": task_ids,
                "mapped_task_evidence_refs": evidence_refs,
                "promotion_authority": False,
                "may_self_sign": False,
                "may_mutate_maturity": False,
            }
        )

    eligible_keys = [
        row["volume_key"]
        for row in records
        if row["target_floor_eligible"]
    ]
    blocked_keys = [
        row["volume_key"]
        for row in records
        if not row["target_floor_eligible"]
    ]

    ledger: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-maturity-closure-ledger-v1",
        "non_authoritative": True,
        "promotion_authority": False,
        "may_self_sign": False,
        "may_mutate_maturity": False,
        "source_reconciliation_digest": reconciliation["report_digest"],
        "primary_volume_count": len(records),
        "target_floor_eligible_count": len(eligible_keys),
        "blocked_volume_count": len(blocked_keys),
        "target_floor_eligible_volume_keys": eligible_keys,
        "blocked_volume_keys": blocked_keys,
        "required_action_counts": action_counts,
        "lane_summary": dict(sorted(lane_counts.items())),
        "records": records,
    }
    ledger["ledger_digest"] = _canonical_digest(ledger)
    return ledger


def _canonical_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=LEDGER,
        help="Ledger output path relative to repository root.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the selected output differs from the generated ledger.",
    )
    args = parser.parse_args(argv)

    try:
        ledger = build_ledger(ROOT)
    except ClosureLedgerError as exc:
        print(f"P1 maturity closure ledger: rejected: {exc}", file=sys.stderr)
        return 2

    output = args.out
    if not output.is_absolute():
        output = ROOT / output
    expected = _canonical_text(ledger)

    if args.check:
        try:
            actual = output.read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"P1 maturity closure ledger: cannot read {output}: {exc}",
                file=sys.stderr,
            )
            return 1
        if actual != expected:
            print(
                "P1 maturity closure ledger: drift detected",
                file=sys.stderr,
            )
            return 1
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(expected, encoding="utf-8")

    print(
        "P1 maturity closure ledger: OK "
        f"({ledger['primary_volume_count']} primary, "
        f"{ledger['target_floor_eligible_count']} eligible, "
        f"{ledger['blocked_volume_count']} blocked)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
