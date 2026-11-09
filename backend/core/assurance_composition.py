"""Safe composition for deterministic assurance reports.

Extensions may add independent invariant families without teaching the base assurance
engine about every subsystem. Composition verifies the base report first, validates
each added invariant strictly, then recomputes posture, counters, and attestation using
the same canonical contract as ``core.system_assurance.verify_assurance``.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Iterable

from core.system_assurance import AssuranceInvariant, AssuranceReport, verify_assurance


def _digest(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def extend_assurance(
    report: AssuranceReport,
    invariants: Iterable[AssuranceInvariant],
) -> AssuranceReport:
    if not isinstance(report, AssuranceReport) or not verify_assurance(report):
        raise ValueError("base assurance report failed verification")
    additions = tuple(invariants)
    for row in additions:
        if not isinstance(row, AssuranceInvariant):
            raise ValueError("assurance extension contains unsupported invariant")
        if not isinstance(row.id, str) or not row.id or row.id != row.id.strip():
            raise ValueError("assurance invariant id must be canonical non-empty text")
        if row.severity not in {"hard", "warning"}:
            raise ValueError("assurance invariant severity must be hard or warning")
        if type(row.passed) is not bool:
            raise ValueError("assurance invariant passed must be boolean")
        if not isinstance(row.detail, str) or not row.detail:
            raise ValueError("assurance invariant detail must be non-empty text")

    combined = report.invariants + additions
    ids = [row.id for row in combined]
    if len(ids) != len(set(ids)):
        raise ValueError("assurance invariant ids must be unique")

    hard_failures = sum(not row.passed for row in combined if row.severity == "hard")
    warnings = sum(not row.passed for row in combined if row.severity == "warning")
    posture = "blocked" if hard_failures else ("degraded" if warnings else "healthy")
    payload = {
        "posture": posture,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "native_coverage_pct": report.native_coverage_pct,
        "readiness_pct": report.readiness_pct,
        "invariants": [asdict(row) for row in combined],
    }
    return AssuranceReport(
        posture,
        hard_failures,
        warnings,
        report.native_coverage_pct,
        report.readiness_pct,
        combined,
        _digest(payload),
    )
