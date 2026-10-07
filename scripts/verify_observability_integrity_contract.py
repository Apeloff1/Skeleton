#!/usr/bin/env python3
"""Fail-closed verifier for G023 observability integrity."""

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
    path = ROOT / "machine/observability_integrity_contract.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"G023 observability integrity: rejected: {exc}", file=sys.stderr)
        return 2
    if contract.get("schema_version") != "skeleton.ai.observability_integrity_contract.v1":
        errors.append("G023 schema drift")
    if contract.get("status") != "active":
        errors.append("G023 contract must be active")
    if contract.get("gap_id") != "G023":
        errors.append("G023 gap identity drift")
    if contract.get("completion_authority") is not False:
        errors.append("G023 implementation cannot self-grant completion")
    canonical = ROOT / "skeleton/observability/integrity.py"
    mirror = ROOT / "skeleton/ai/runtime/observability/integrity.py"
    if not canonical.is_file() or not mirror.is_file():
        errors.append("G023 canonical or governed AI runtime missing")
    elif canonical.read_bytes() != mirror.read_bytes():
        errors.append("G023 canonical/governed AI runtime drift")
    if canonical.is_file():
        source = canonical.read_text(encoding="utf-8")
        for marker in (
            "class ObservabilityIntegrityMonitor",
            "heartbeat-stale-or-missing",
            "sequence-gap-budget-exceeded",
            "cardinality-budget-exceeded",
            "def audit_resilient_telemetry",
            "def expect_trace",
            "canonical_state_dependency",
        ):
            if marker not in source:
                errors.append(f"G023 integrity runtime missing marker: {marker}")
    result = {
        "schema_version": "skeleton.ai.observability_integrity_verifier.v1",
        "gap_id": "G023",
        "valid": not errors,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    else:
        print("G023 observability integrity: OK")
    return 0 if not errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
