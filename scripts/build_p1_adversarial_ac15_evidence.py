#!/usr/bin/env python3
"""Build exact-head evidence for AC-15 economic denial/budget overshoot."""

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
AXIS_ID = "AC-15"
BATCH_ID = "p1-adversarial-ac15-evidence"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "budget_fault",
    "fanout_stress",
    "quota_isolation",
    "provider_reprice_simulation",
)

PROOF_ANCHORS: dict[str, tuple[str, ...]] = {
    "budget_fault": (
        "skeleton/testing/test_adversarial_ac15.py",
        "skeleton/intelligence/admission.py",
        "skeleton/testing/test_cost_admission.py",
    ),
    "fanout_stress": (
        "skeleton/testing/test_adversarial_ac15.py",
        "skeleton/intelligence/quota.py",
        "skeleton/intelligence/shared_pressure.py",
        "skeleton/testing/test_shared_pressure.py",
    ),
    "quota_isolation": (
        "skeleton/testing/test_adversarial_ac15.py",
        "skeleton/intelligence/quota.py",
        "skeleton/intelligence/quota_sqlite.py",
        "skeleton/testing/test_tenant_quota_sqlite.py",
    ),
    "provider_reprice_simulation": (
        "skeleton/testing/test_adversarial_ac15.py",
        "skeleton/provider_runtime.py",
        "scripts/verify_cost_admission_closure.py",
        "tests/test_cost_admission_independent_verifier.py",
    ),
}


class AC15EvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC15EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC15EvidenceError(f"{path} must contain an object")
    return value


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _anchor(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise AC15EvidenceError(f"invalid proof anchor: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if tracked.returncode != 0:
        raise AC15EvidenceError(f"untracked proof anchor: {relative}")
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def build_ac15_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC15EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC15EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in axes
            if isinstance(row, dict) and row.get("id") == AXIS_ID
        ),
        None,
    )
    if axis is None:
        raise AC15EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC15EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC15EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    records = registry.get("records")
    if not isinstance(records, list):
        raise AC15EvidenceError("risk registry records must be a list")
    bound_ids = {
        row.get("obligation_id")
        for row in records
        if isinstance(row, dict)
    }
    if obligation.obligation_id in bound_ids:
        raise AC15EvidenceError(f"{AXIS_ID} is already governed")

    proof_modes: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        proof = {
            "axis_id": AXIS_ID,
            "mode": mode,
            "expected_head": expected_head,
            "anchors": [_anchor(root, p) for p in PROOF_ANCHORS[mode]],
        }
        proof["proof_digest"] = _digest(proof)
        proof_modes[mode] = proof
        evidence.append(
            {
                "source": (
                    f"p1:adversarial-ac15-evidence:{AXIS_ID}:"
                    f"{mode}:{expected_head}"
                ),
                "digest": proof["proof_digest"],
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
        "evidence": evidence,
        "proof_modes": proof_modes,
        "non_authoritative": True,
        "creates_binding": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
    }
    candidate["candidate_digest"] = _digest(candidate)

    report = {
        "schema_version": 1,
        "engine": "p1-adversarial-ac15-evidence-v1",
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
    }
    report["report_digest"] = _digest(report)
    return report


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_ac15_evidence(ROOT, expected_head=args.expected_head)
    except AC15EvidenceError as exc:
        print(f"P1 AC-15 evidence: rejected: {exc}", file=sys.stderr)
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

    print("P1 AC-15 evidence: OK (1 candidate, 4 exact-head modes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
