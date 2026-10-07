#!/usr/bin/env python3
"""Validate the canonical P1 terminal-closure manifest.

The legacy P1 execution map and backlog intentionally remain status=active
because their schema represents the planning/provenance ledger. This verifier
provides one unambiguous terminal authority over the bounded P1 frontier and
fails closed if the evidence registry, scope partition, or canonical P1 gap
closure drifts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from scripts.verify_p1_terminal_closure import verify_repository as verify_gap_closure


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/ai_p1_terminal_closure.json")
EXECUTION_MAP = Path("machine/ai_p1_execution_map.json")
RISK_REGISTRY = Path("machine/p1_risk_evidence_bindings.json")


class ClosureManifestError(RuntimeError):
    pass


def _load(root: Path, rel: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureManifestError(f"cannot read {rel}") from exc
    if not isinstance(value, dict):
        raise ClosureManifestError(f"{rel} must contain an object")
    return value


def validate_repository(root: Path = ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    manifest = _load(root, MANIFEST)
    p1 = _load(root, EXECUTION_MAP)
    risk = _load(root, RISK_REGISTRY)

    if manifest.get("schema_version") != 1:
        errors.append("P1 terminal closure schema_version must be 1")
    if manifest.get("status") != "closed":
        errors.append("P1 terminal closure manifest must be closed")
    if manifest.get("claim_scope") != "bounded_trustworthy_production_frontier":
        errors.append("P1 terminal closure claim scope drift")

    frontier = manifest.get("frontier")
    scope = p1.get("scope_summary")
    if not isinstance(frontier, dict) or not isinstance(scope, dict):
        errors.append("P1 frontier/scope objects are required")
    else:
        expected = {
            "masterplan_volume_count": scope.get("masterplan_volume_count"),
            "primary_p1_frontier_volume_count": scope.get(
                "primary_p1_frontier_volume_count"
            ),
            "deferred_to_p2_volume_count": scope.get("deferred_volume_count"),
        }
        for key, value in expected.items():
            if frontier.get(key) != value:
                errors.append(f"P1 terminal frontier {key} drift")
        if expected != {
            "masterplan_volume_count": 421,
            "primary_p1_frontier_volume_count": 107,
            "deferred_to_p2_volume_count": 314,
        }:
            errors.append("P1 canonical 421/107/314 scope partition drift")
        deferred = scope.get("deferred_volume_refs")
        if not isinstance(deferred, list) or len(set(map(str, deferred))) != 314:
            errors.append("P1 deferred-to-P2 set must contain 314 unique refs")

    semantics = manifest.get("planning_ledger_semantics")
    if not isinstance(semantics, dict):
        errors.append("P1 planning-ledger semantics are required")
    else:
        if p1.get("status") != semantics.get("execution_map_status"):
            errors.append("P1 execution-map planning status drift")
        if semantics.get("execution_map_status") != "active":
            errors.append("P1 execution-map planning status must remain active")
        if semantics.get("task_backlog_status") != "active":
            errors.append("P1 task-backlog planning status must remain active")

    required = manifest.get("risk_evidence")
    records = risk.get("records")
    if not isinstance(required, dict) or not isinstance(records, list):
        errors.append("P1 risk evidence manifest/registry is malformed")
        records = []
    else:
        expected_count = required.get("required_obligation_count")
        if expected_count != 513 or len(records) != expected_count:
            errors.append(
                f"P1 risk obligation count drift: expected=513 actual={len(records)}"
            )

    ids: set[str] = set()
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            errors.append(f"P1 risk record {index} must be an object")
            continue
        oid = row.get("obligation_id")
        if not isinstance(oid, str) or not oid:
            errors.append(f"P1 risk record {index} missing obligation_id")
        elif oid in ids:
            errors.append(f"P1 duplicate risk obligation: {oid}")
        else:
            ids.add(oid)
        if row.get("disposition") != "evidence":
            errors.append(f"P1 risk obligation is not evidence-closed: {oid}")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"P1 risk obligation has no evidence: {oid}")
        if row.get("accepted_risk") is not None:
            errors.append(f"P1 accepted-risk substitution is forbidden: {oid}")

    gap_receipt = verify_gap_closure(root)
    if not gap_receipt.get("valid"):
        errors.extend(
            "terminal-gap:" + str(item)
            for item in gap_receipt.get("errors", [])
        )

    handoff = manifest.get("handoff")
    if not isinstance(handoff, dict):
        errors.append("P1->P2 handoff is required")
    else:
        if handoff.get("next_phase") != "P2":
            errors.append("P1 terminal handoff must target P2")
        if handoff.get("expected_volume_count") != 314:
            errors.append("P1 terminal handoff must preserve 314 deferred volumes")

    report = {
        "schema_version": 1,
        "status": "closed" if not errors else "rejected",
        "p1_frontier": "107/107",
        "risk_obligations": f"{len(records)}/513",
        "deferred_to_p2": 314,
        "terminal_gap_valid": bool(gap_receipt.get("valid")),
        "errors": errors,
        "valid": not errors,
    }
    return errors, report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        errors, report = validate_repository(ROOT)
    except ClosureManifestError as exc:
        print(f"P1 terminal closure manifest: rejected: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    if errors:
        if not args.json:
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        return 1
    if not args.json:
        print("P1 terminal closure manifest: OK (107/107 frontier, 513/513 evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
