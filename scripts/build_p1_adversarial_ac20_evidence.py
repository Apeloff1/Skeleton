#!/usr/bin/env python3
"""Build exact-head evidence for AC-20 plan/machine/implementation drift.

This verifier is intentionally non-authoritative. It proves the four evidence
modes required by AC-20 from executable repository validators and tracked
proof anchors, then emits one candidate binding packet. It never mutates the
governed risk registry, accepts risk, or promotes maturity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_p1_risk_evidence import (  # noqa: E402
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
)

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
AXIS_ID = "AC-20"
BATCH_ID = "p1-adversarial-ac20-evidence"
OWNER_ID = "ACC-P1-EVID-04"
CATEGORY_PREFIX = "p1_adversarial_ac20"
EXPECTED_MODES = (
    "drift_validator",
    "architecture_fitness",
    "undeclared_component_scan",
    "traceability_check",
)

PROOF_ANCHORS: dict[str, tuple[str, ...]] = {
    "drift_validator": (
        "scripts/check_ai_master_plan.py",
        "scripts/check_ai_file_tree.py",
        "scripts/check_state_topology.py",
    ),
    "architecture_fitness": (
        "scripts/check_architecture_map.py",
        "scripts/check_ai_app_construction.py",
        "scripts/check_capability_interfaces.py",
    ),
    "undeclared_component_scan": (
        "scripts/check_ai_file_tree.py",
        "scripts/check_capability_interfaces.py",
        "scripts/check_state_topology.py",
    ),
    "traceability_check": (
        "scripts/check_ai_build_accountability.py",
        "scripts/check_ai_master_build_sequence.py",
        "scripts/check_ai_engineering_task_matrix.py",
        "scripts/check_ai_execution_frontier.py",
    ),
}


class AC20EvidenceError(RuntimeError):
    """AC-20 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC20EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC20EvidenceError(f"{path} must contain an object")
    return value


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked_anchor(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise AC20EvidenceError(f"proof anchor is missing: {relative}")
    if path.is_symlink():
        raise AC20EvidenceError(f"proof anchor must not be symlinked: {relative}")

    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise AC20EvidenceError(f"proof anchor is not tracked: {relative}")

    return {
        "path": relative,
        "sha256": _file_digest(path),
    }


def build_ac20_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC20EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC20EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in axes
            if isinstance(row, dict) and row.get("id") == AXIS_ID
        ),
        None,
    )
    if axis is None:
        raise AC20EvidenceError(f"{AXIS_ID} is missing from adversarial closure")

    modes = axis.get("required_evidence_modes")
    if tuple(modes or ()) != EXPECTED_MODES:
        raise AC20EvidenceError(
            f"{AXIS_ID} evidence modes drifted: {modes!r}"
        )

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC20EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    records = registry.get("records")
    if not isinstance(records, list):
        raise AC20EvidenceError("risk registry records must be a list")
    bound_ids = {
        row.get("obligation_id")
        for row in records
        if isinstance(row, dict)
    }
    if obligation.obligation_id in bound_ids:
        raise AC20EvidenceError(f"{AXIS_ID} is already governed")

    proof_modes: dict[str, dict[str, Any]] = {}
    evidence_refs: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        anchors = [
            _tracked_anchor(root, relative)
            for relative in PROOF_ANCHORS[mode]
        ]
        proof = {
            "axis_id": AXIS_ID,
            "mode": mode,
            "expected_head": expected_head,
            "anchors": anchors,
        }
        proof_digest = _canonical_digest(proof)
        proof["proof_digest"] = proof_digest
        proof_modes[mode] = proof
        evidence_refs.append(
            {
                "source": (
                    f"p1:adversarial-ac20-evidence:{AXIS_ID}:"
                    f"{mode}:{expected_head}"
                ),
                "digest": proof_digest,
                "category": mode,
            }
        )

    candidate = {
        "batch_id": BATCH_ID,
        "axis_id": AXIS_ID,
        "axis_name": axis.get("name"),
        "statement": obligation.statement,
        "obligation_id": obligation.obligation_id,
        "obligation_digest": obligation.obligation_digest,
        "owner_id": OWNER_ID,
        "recommended_severity": "high",
        "recommended_disposition": "evidence",
        "expected_head": expected_head,
        "required_evidence_modes": list(EXPECTED_MODES),
        "evidence": evidence_refs,
        "proof_modes": proof_modes,
        "non_authoritative": True,
        "creates_binding": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
    }
    candidate["candidate_digest"] = _canonical_digest(candidate)

    return {
        "schema_version": 1,
        "engine": "p1-adversarial-ac20-evidence-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "axis_id": AXIS_ID,
        "candidate_count": 1,
        "required_evidence_mode_count": len(EXPECTED_MODES),
        "non_authoritative": True,
        "creates_bindings": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
        "candidate": candidate,
        "report_digest": _canonical_digest(candidate),
    }


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_ac20_evidence(ROOT, expected_head=args.expected_head)
    except AC20EvidenceError as exc:
        print(f"P1 AC-20 evidence: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_render(report), encoding="utf-8")

    if args.print_summary:
        print(
            json.dumps(
                {
                    "axis_id": report["axis_id"],
                    "candidate_count": report["candidate_count"],
                    "required_evidence_mode_count": report[
                        "required_evidence_mode_count"
                    ],
                    "expected_head": report["expected_head"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )

    print("P1 AC-20 evidence: OK (1 candidate, 4 exact-head modes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
