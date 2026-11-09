#!/usr/bin/env python3
"""Fail-closed verifier for the canonical hostile-gap disposition ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
AUDIT = Path("docs/architecture/masterplan-gap-audit.md")
LEDGER = Path("machine/ai_hostile_gap_disposition.json")
ALLOWED = {
    "open",
    "implementation_pr_open",
    "landed_unverified",
    "verified_closed",
    "superseded",
}
ROW = re.compile(r"^\|\s*(G\d{3})\s*\|\s*(P[012])\s*\|\s*([^|]+)\|")
PR_REF = re.compile(r"^github:pr#([1-9]\d*)$")


class GapDispositionError(RuntimeError):
    pass


def _load_json(root: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GapDispositionError(f"cannot read {LEDGER}") from exc
    if not isinstance(value, dict):
        raise GapDispositionError("gap disposition ledger must be an object")
    return value


def _audit_rows(root: Path) -> dict[str, tuple[str, str]]:
    try:
        lines = (root / AUDIT).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise GapDispositionError(f"cannot read {AUDIT}") from exc
    rows: dict[str, tuple[str, str]] = {}
    for line in lines:
        match = ROW.match(line)
        if not match:
            continue
        gap_id, severity, title = match.groups()
        title = title.strip()
        prior = rows.get(gap_id)
        current = (severity, title)
        if prior is not None and prior != current:
            raise GapDispositionError(f"{gap_id} has conflicting audit definitions")
        rows[gap_id] = current
    return rows


def validate(root: Path = ROOT) -> dict[str, Any]:
    ledger = _load_json(root)
    audit = _audit_rows(root)
    errors: list[str] = []

    if ledger.get("schema_version") != "skeleton.ai.hostile_gap_disposition.v1":
        errors.append("gap disposition schema drift")
    if ledger.get("authority") != AUDIT.as_posix():
        errors.append("gap disposition authority drift")
    if set(ledger.get("allowed_states", [])) != ALLOWED:
        errors.append("allowed disposition states drift")

    raw_gaps = ledger.get("gaps")
    if not isinstance(raw_gaps, list):
        errors.append("gaps must be a list")
        raw_gaps = []

    by_id: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for item in raw_gaps:
        if not isinstance(item, dict):
            errors.append("every gap disposition must be an object")
            continue
        gap_id = item.get("id")
        if not isinstance(gap_id, str):
            errors.append("gap disposition id must be text")
            continue
        if gap_id in by_id:
            duplicates.append(gap_id)
        by_id[gap_id] = item
    if duplicates:
        errors.append("duplicate gap ids: " + ", ".join(sorted(set(duplicates))))

    audit_ids = set(audit)
    ledger_ids = set(by_id)
    missing = sorted(audit_ids - ledger_ids)
    extra = sorted(ledger_ids - audit_ids)
    if missing:
        errors.append("ledger missing audit gaps: " + ", ".join(missing))
    if extra:
        errors.append("ledger contains unknown gaps: " + ", ".join(extra))
    if len(audit) != 200:
        errors.append(f"canonical audit must contain 200 gaps, found {len(audit)}")

    status_counts = {state: 0 for state in sorted(ALLOWED)}
    severity_counts = {"P0": 0, "P1": 0, "P2": 0}
    for gap_id, (severity, title) in sorted(audit.items()):
        item = by_id.get(gap_id)
        if item is None:
            continue
        if item.get("severity") != severity:
            errors.append(f"{gap_id} severity drift")
        if item.get("title") != title:
            errors.append(f"{gap_id} title drift")
        severity_counts[severity] += 1

        status = item.get("status")
        if status not in ALLOWED:
            errors.append(f"{gap_id} has invalid status {status!r}")
            continue
        status_counts[status] += 1

        implementation_refs = item.get("implementation_refs")
        evidence_refs = item.get("evidence_refs")
        if not isinstance(implementation_refs, list) or any(
            not isinstance(ref, str) for ref in implementation_refs
        ):
            errors.append(f"{gap_id} implementation_refs must be a text list")
            implementation_refs = []
        if not isinstance(evidence_refs, list) or any(
            not isinstance(ref, str) for ref in evidence_refs
        ):
            errors.append(f"{gap_id} evidence_refs must be a text list")
            evidence_refs = []

        if status == "implementation_pr_open":
            if not implementation_refs:
                errors.append(f"{gap_id} implementation_pr_open requires PR reference")
            for ref in implementation_refs:
                if PR_REF.fullmatch(ref) is None:
                    errors.append(f"{gap_id} has noncanonical implementation PR ref {ref!r}")
            if evidence_refs:
                errors.append(f"{gap_id} open PR state cannot claim closure evidence")

        if status == "landed_unverified" and not implementation_refs:
            errors.append(f"{gap_id} landed_unverified requires implementation reference")

        if status == "verified_closed":
            if not implementation_refs:
                errors.append(f"{gap_id} verified_closed requires implementation reference")
            if not evidence_refs:
                errors.append(f"{gap_id} verified_closed requires evidence")
            if not item.get("closure_note"):
                errors.append(f"{gap_id} verified_closed requires closure_note")

        if status == "open" and evidence_refs:
            errors.append(f"{gap_id} open state cannot carry closure evidence")

    summary = ledger.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
        summary = {}
    expected_summary = {
        "total": len(audit),
        "p0": severity_counts["P0"],
        "p1": severity_counts["P1"],
        "p2": severity_counts["P2"],
        "implementation_pr_open": status_counts["implementation_pr_open"],
        "verified_closed": status_counts["verified_closed"],
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(
                f"summary {key} drift: expected {expected}, got {summary.get(key)!r}"
            )

    return {
        "schema_version": "skeleton.ai.hostile_gap_disposition_receipt.v1",
        "valid": not errors,
        "status": "valid" if not errors else "rejected",
        "audit_gap_count": len(audit),
        "severity_counts": severity_counts,
        "status_counts": status_counts,
        "errors": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(ROOT)
    except GapDispositionError as exc:
        print(f"AI hostile gap disposition: rejected: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["valid"]:
        print(
            "AI hostile gap disposition: OK "
            f"({result['audit_gap_count']} gaps; "
            f"{result['status_counts']['implementation_pr_open']} implementation PRs open)"
        )
    else:
        for error in result["errors"]:
            print(f"  - {error}", file=sys.stderr)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
