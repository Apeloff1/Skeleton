#!/usr/bin/env python3
"""Fail-closed verifier for G016 privacy deletion propagation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.persistence.privacy_deletion import REQUIRED_TARGET_CLASSES


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine/privacy_deletion_contract.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    try:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"G016 privacy deletion: rejected: {exc}", file=sys.stderr)
        return 2

    if not isinstance(contract, dict):
        errors.append("privacy deletion contract must be an object")
        contract = {}
    if contract.get("schema_version") != "skeleton.ai.privacy_deletion_contract.v1":
        errors.append("privacy deletion schema drift")
    if contract.get("status") != "active":
        errors.append("privacy deletion contract must be active")
    if contract.get("gap_id") != "G016":
        errors.append("privacy deletion gap identity drift")
    if contract.get("completion_authority") is not False:
        errors.append("implementation contract cannot self-grant completion")

    expected = tuple(sorted(REQUIRED_TARGET_CLASSES))
    declared = contract.get("required_target_classes")
    if not isinstance(declared, list) or tuple(declared) != expected:
        errors.append("required deletion target classes drift")

    pairs = (
        (
            "skeleton/persistence/privacy_deletion.py",
            "skeleton/ai/runtime/persistence/privacy_deletion.py",
        ),
        (
            "skeleton/jeeves/agent/memory.py",
            "skeleton/ai/agents/jeeves/agent/memory.py",
        ),
        (
            "skeleton/jeeves/agent/context_repository.py",
            "skeleton/ai/agents/jeeves/agent/context_repository.py",
        ),
    )
    for canonical, mirror in pairs:
        left = ROOT / canonical
        right = ROOT / mirror
        if not left.is_file():
            errors.append(f"canonical G016 surface missing: {canonical}")
            continue
        if not right.is_file():
            errors.append(f"governed AI mirror missing: {mirror}")
            continue
        if left.read_bytes() != right.read_bytes():
            errors.append(f"G016 canonical/AI mirror drift: {canonical}")

    markers = {
        "skeleton/persistence/privacy_deletion.py": (
            "assert_materialization_allowed",
            "discover_copy",
            "acknowledge_resolution",
            "record_scan",
            "PROVENANCE_REFERENCE",
        ),
        "skeleton/jeeves/agent/memory.py": (
            "privacy_delete_subject",
            "privacy_tombstone_receipt",
            "privacy-deleted subject cannot be materialized",
        ),
        "skeleton/jeeves/agent/context_repository.py": (
            "privacy_delete_all",
            "privacy_deletion_receipt",
            "privacy-deleted context repository is sealed",
            "self._patches.clear()",
        ),
    }
    for path, required in markers.items():
        source_path = ROOT / path
        if not source_path.is_file():
            continue
        source = source_path.read_text(encoding="utf-8")
        for marker in required:
            if marker not in source:
                errors.append(f"{path} missing G016 marker: {marker}")

    result = {
        "schema_version": "skeleton.ai.privacy_deletion_verifier.v1",
        "gap_id": "G016",
        "valid": not errors,
        "target_class_count": len(REQUIRED_TARGET_CLASSES),
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    else:
        print(
            "G016 privacy deletion: OK "
            f"({len(REQUIRED_TARGET_CLASSES)} target classes)"
        )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
