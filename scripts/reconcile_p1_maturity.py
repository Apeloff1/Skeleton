#!/usr/bin/env python3
"""Emit deterministic P1 maturity candidates without mutating canonical state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.maturity_reconciliation import (
    MaturityReconciliationError,
    reconcile_volume,
)


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
ACCOUNTABILITY = Path("machine/ai_build_accountability.json")
P1_MAP = Path("machine/ai_p1_execution_map.json")


class ReconciliationError(RuntimeError):
    """Repository reconciliation inputs are malformed."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise ReconciliationError(f"{path} must contain an object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def reconcile_repository(
    root: Path = ROOT,
    *,
    selected_volumes: tuple[str, ...] = (),
) -> dict[str, Any]:
    paths = {
        "master_plan": root / MASTER,
        "accountability": root / ACCOUNTABILITY,
        "p1_execution_map": root / P1_MAP,
        "engine_contract": root / "skeleton/contracts/maturity_reconciliation.py",
        "engine_runner": root / "scripts/reconcile_p1_maturity.py",
    }
    before = {name: _digest(path) for name, path in paths.items()}
    master = _load(paths["master_plan"])
    accountability = _load(paths["accountability"])
    p1_map = _load(paths["p1_execution_map"])

    authority = master.get("authority")
    if not isinstance(authority, dict):
        raise ReconciliationError("master plan authority must be an object")
    expected_authority = {
        "p1_maturity_reconciliation_engine": str(Path("scripts/reconcile_p1_maturity.py")),
        "p1_maturity_reconciliation_contract": str(Path("skeleton/contracts/maturity_reconciliation.py")),
    }
    for key, expected in expected_authority.items():
        if authority.get(key) != expected:
            raise ReconciliationError(
                f"master plan {key} authority pointer drift"
            )

    volumes = master.get("volumes")
    policy = master.get("volume_maturity_policy")
    records = accountability.get("records")
    lanes = p1_map.get("lanes")
    if not isinstance(volumes, list):
        raise ReconciliationError("master plan volumes must be a list")
    if not isinstance(policy, dict):
        raise ReconciliationError("volume_maturity_policy must be an object")
    if not isinstance(records, list):
        raise ReconciliationError("accountability records must be a list")
    if not isinstance(lanes, list):
        raise ReconciliationError("P1 lanes must be a list")

    volume_by_key = {
        str(row.get("key")): row
        for row in volumes
        if isinstance(row, dict) and row.get("key")
    }
    record_by_id = {
        str(row.get("id")): row
        for row in records
        if isinstance(row, dict) and row.get("id")
    }

    owner: dict[str, dict[str, Any]] = {}
    for lane in lanes:
        if not isinstance(lane, dict):
            raise ReconciliationError("P1 lane entries must be objects")
        target = lane.get("target_maturity")
        lane_id = lane.get("id")
        refs = lane.get("primary_volume_refs")
        if not isinstance(lane_id, str) or not isinstance(target, str):
            raise ReconciliationError("P1 lane identity/target is malformed")
        if not isinstance(refs, list):
            raise ReconciliationError(f"{lane_id}: primary_volume_refs must be a list")
        for raw_ref in refs:
            ref = str(raw_ref)
            if ref in owner:
                raise ReconciliationError(f"duplicate P1 primary owner: {ref}")
            owner[ref] = {
                "lane_id": lane_id,
                "target_maturity": target,
            }

    requested = tuple(dict.fromkeys(selected_volumes))
    if requested:
        unknown = [key for key in requested if key not in owner]
        if unknown:
            raise ReconciliationError(
                "requested volumes are outside P1 primary scope: "
                + ",".join(sorted(unknown))
            )
        keys = sorted(requested)
    else:
        keys = sorted(owner)

    rows: list[dict[str, Any]] = []
    for key in keys:
        volume = volume_by_key.get(key)
        if volume is None:
            raise ReconciliationError(f"missing masterplan volume: {key}")
        accountability_id = volume.get("accountability_id")
        record = record_by_id.get(str(accountability_id))
        if record is None:
            raise ReconciliationError(
                f"{key}: missing accountability record {accountability_id}"
            )
        lane = owner[key]
        try:
            decision = reconcile_volume(
                volume,
                record,
                policy,
                target_floor=lane["target_maturity"],
            )
        except MaturityReconciliationError as exc:
            raise ReconciliationError(str(exc)) from exc
        payload = decision.as_dict()
        payload["lane_id"] = lane["lane_id"]
        rows.append(payload)

    after = {name: _digest(path) for name, path in paths.items()}
    if before != after:
        raise ReconciliationError(
            "canonical source files changed during reconciliation"
        )

    candidate_count = sum(
        1 for row in rows if row["promotion_candidate"] is not None
    )
    floor_ready_count = sum(
        1 for row in rows if row["target_floor_eligible"] is True
    )
    current_counts: dict[str, int] = {}
    candidate_counts: dict[str, int] = {}
    for row in rows:
        current = row["current_status"]
        current_counts[current] = current_counts.get(current, 0) + 1
        candidate = row["promotion_candidate"] or "none"
        candidate_counts[candidate] = candidate_counts.get(candidate, 0) + 1

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-maturity-reconciliation-v1",
        "source_digests": before,
        "source_mutation_detected": False,
        "volume_count": len(rows),
        "promotion_candidate_count": candidate_count,
        "target_floor_eligible_count": floor_ready_count,
        "current_status_counts": dict(sorted(current_counts.items())),
        "promotion_candidate_counts": dict(sorted(candidate_counts.items())),
        "records": rows,
    }
    report["report_digest"] = _canonical_digest(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--volume",
        action="append",
        default=[],
        help="Restrict reconciliation to a P1 primary volume key.",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-report", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = reconcile_repository(
            ROOT,
            selected_volumes=tuple(args.volume),
        )
    except ReconciliationError as exc:
        print(f"P1 maturity reconciliation: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_report:
        print(json.dumps(report, indent=2, sort_keys=True))
    print(
        "P1 maturity reconciliation: OK "
        f"({report['volume_count']} volumes, "
        f"{report['promotion_candidate_count']} candidates, "
        f"{report['target_floor_eligible_count']} at lane floor)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
