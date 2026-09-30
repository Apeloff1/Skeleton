#!/usr/bin/env python3
"""Build exact-head evidence for AC-14 evidence integrity and verifier independence."""

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
AXIS_ID = "AC-14"
BATCH_ID = "p1-adversarial-ac14-evidence"
OWNER_ID = "ACC-P1-EVID-04"
WORKFLOW = Path(".github/workflows/p1-adversarial-ac14-evidence.yml")
EXPECTED_MODES = (
    "evidence_digest_check",
    "independent_verification",
    "failed_run_retention",
    "provenance_replay",
)

PROOF_ANCHORS: dict[str, tuple[str, ...]] = {
    "evidence_digest_check": (
        "skeleton/contracts/canonical.py",
        "skeleton/contracts/risk_evidence.py",
        "scripts/build_p1_bulk_volume_obligation_evidence.py",
    ),
    "independent_verification": (
        "scripts/verify_provider_surface_closure.py",
        "tests/test_provider_surface_independent_verifier.py",
        "scripts/verify_cost_admission_closure.py",
        "tests/test_cost_admission_independent_verifier.py",
    ),
    "failed_run_retention": (
        str(WORKFLOW),
    ),
    "provenance_replay": (
        "scripts/build_p1_bulk_volume_obligation_evidence.py",
        "scripts/build_p1_adversarial_ac20_evidence.py",
        "scripts/build_p1_adversarial_ac15_evidence.py",
    ),
}


class AC14EvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC14EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC14EvidenceError(f"{path} must contain an object")
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
        raise AC14EvidenceError(f"invalid proof anchor: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if tracked.returncode != 0:
        raise AC14EvidenceError(f"untracked proof anchor: {relative}")
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _validate_retention_contract(root: Path) -> dict[str, Any]:
    source = (root / WORKFLOW).read_text(encoding="utf-8")
    required = (
        "uses: actions/upload-artifact@",
        "if: always()",
        "retention-days: 30",
        "name: ac14-evidence-",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AC14EvidenceError(
            "AC-14 failed-run retention contract is incomplete: "
            + ",".join(missing)
        )
    return {
        "workflow": str(WORKFLOW),
        "required_tokens": list(required),
        "workflow_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }


def build_ac14_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC14EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC14EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in axes
            if isinstance(row, dict) and row.get("id") == AXIS_ID
        ),
        None,
    )
    if axis is None:
        raise AC14EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC14EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC14EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    records = registry.get("records")
    if not isinstance(records, list):
        raise AC14EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in records
    )

    retention = _validate_retention_contract(root)
    proof_modes: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, str]] = []

    for mode in EXPECTED_MODES:
        proof = {
            "axis_id": AXIS_ID,
            "mode": mode,
            "expected_head": expected_head,
            "anchors": [_anchor(root, p) for p in PROOF_ANCHORS[mode]],
        }
        if mode == "failed_run_retention":
            proof["retention_contract"] = retention
        proof["proof_digest"] = _digest(proof)
        proof_modes[mode] = proof
        evidence.append(
            {
                "source": (
                    f"p1:adversarial-ac14-evidence:{AXIS_ID}:"
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
        "binding_present": binding_present,
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
        "engine": "p1-adversarial-ac14-evidence-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "axis_id": AXIS_ID,
        "candidate_count": 1,
        "already_bound_count": int(binding_present),
        "candidate_binding_count": 0 if binding_present else 1,
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
        report = build_ac14_evidence(ROOT, expected_head=args.expected_head)
    except AC14EvidenceError as exc:
        print(f"P1 AC-14 evidence: rejected: {exc}", file=sys.stderr)
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

    print("P1 AC-14 evidence: OK (1 candidate, 4 exact-head modes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
