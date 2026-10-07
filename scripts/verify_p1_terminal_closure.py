#!/usr/bin/env python3
"""Independently verify terminal closure of the canonical P1 gap set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION = Path("machine/ai_app_construction.json")

EXPECTED_P1_GAPS = {
    "gap-feedback-promotion",
    "gap-provider-redundancy",
    "gap-release-slo-loop",
}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    path = root / CONSTRUCTION
    construction = _load(path)

    rows = construction.get("gap_register")
    if not isinstance(rows, list):
        raise VerificationError("gap_register must be a list")

    by_id = {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }
    actual_p1 = {
        gap_id
        for gap_id, row in by_id.items()
        if row.get("priority") == "P1"
    }
    if actual_p1 != EXPECTED_P1_GAPS:
        errors.append(
            "canonical P1 inventory mismatch: missing="
            + ",".join(sorted(EXPECTED_P1_GAPS - actual_p1))
            + " unexpected="
            + ",".join(sorted(actual_p1 - EXPECTED_P1_GAPS))
        )

    gap_state: dict[str, str] = {}
    for gap_id in sorted(EXPECTED_P1_GAPS):
        row = by_id.get(gap_id)
        if row is None:
            errors.append(f"missing canonical P1 gap: {gap_id}")
            continue
        state = str(row.get("status") or "")
        gap_state[gap_id] = state
        if state != "closed":
            errors.append(f"P1 gap must remain closed: {gap_id}")
        outstanding = row.get("outstanding_evidence")
        if isinstance(outstanding, list) and outstanding:
            errors.append(f"P1 gap has outstanding evidence: {gap_id}")

    blueprint = construction.get("provider_redundancy_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("provider_redundancy_blueprint is missing")
    else:
        if blueprint.get("gap") != "gap-provider-redundancy":
            errors.append("provider redundancy blueprint gap binding drift")
        if blueprint.get("status") != "closed":
            errors.append("provider redundancy blueprint must remain closed")

    return {
        "schema_version": 1,
        "verifier": "independent-p1-terminal-closure-v1",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "expected_gap_count": len(EXPECTED_P1_GAPS),
        "actual_gap_count": len(actual_p1),
        "gap_state": gap_state,
        "construction_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        print(f"P1 terminal closure: rejected: {exc}", file=sys.stderr)
        return 2

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("P1 terminal closure: FAIL", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "P1 terminal closure: OK "
        f"({receipt['actual_gap_count']}/{receipt['expected_gap_count']} closed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
