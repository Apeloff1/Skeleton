#!/usr/bin/env python3
"""Fail-closed verifier for G022 backpressure propagation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    path = ROOT / "machine/backpressure_contract.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"G022 backpressure: rejected: {exc}", file=sys.stderr)
        return 2

    if contract.get("schema_version") != "skeleton.ai.backpressure_contract.v1":
        errors.append("G022 schema drift")
    if contract.get("status") != "active":
        errors.append("G022 contract must be active")
    if contract.get("gap_id") != "G022":
        errors.append("G022 gap identity drift")
    if contract.get("completion_authority") is not False:
        errors.append("G022 implementation cannot self-grant completion")

    canonical = ROOT / "skeleton/kernel/backpressure.py"
    mirror = ROOT / "skeleton/ai/runtime/kernel/backpressure.py"
    if not canonical.is_file() or not mirror.is_file():
        errors.append("G022 canonical or governed AI runtime missing")
    elif canonical.read_bytes() != mirror.read_bytes():
        errors.append("G022 canonical/governed AI runtime drift")

    if canonical.is_file():
        source = canonical.read_text(encoding="utf-8")
        for marker in (
            "class TokenBucket",
            "class LoadShedder",
            "class BackpressureGovernor",
            "class BackpressureTopology",
            "class PressureObservation",
            "class BackpressurePropagationController",
            "def decision",
            "def _recompute",
            "retry_after_ms",
            "completion_checkbox",
        ):
            if marker not in source:
                errors.append(f"G022 runtime missing marker: {marker}")

    result = {
        "schema_version": "skeleton.ai.backpressure_verifier.v1",
        "gap_id": "G022",
        "valid": not errors,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    else:
        print("G022 backpressure propagation: OK")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
