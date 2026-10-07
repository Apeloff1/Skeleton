#!/usr/bin/env python3
"""Build exact-head evidence for AC-19 human override and operator recovery."""

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

AXIS_ID = "AC-19"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "break_glass_drill",
    "operator_error_simulation",
    "approval_fatigue",
    "undo_recovery",
)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

PROOFS = {
    "break_glass_drill": (
        (
            "skeleton/security/operator_override.py",
            (
                "class OperatorOverrideController",
                "wildcard break-glass scope is forbidden",
                "grant duration exceeds break-glass bound",
            ),
        ),
        (
            "skeleton/testing/test_operator_override.py",
            (
                "test_break_glass_rejects_wildcard_authority",
                "test_break_glass_grant_is_time_bounded_and_scope_bounded",
                "test_grant_use_budget_is_enforced",
            ),
        ),
    ),
    "operator_error_simulation": (
        (
            "skeleton/security/operator_override.py",
            (
                "destructive override requires preview receipt",
                "destructive override preview is missing, stale, or mismatched",
            ),
        ),
        (
            "skeleton/testing/test_operator_override.py",
            (
                "test_destructive_action_requires_matching_recent_preview",
                "test_stale_or_mismatched_preview_fails_closed",
            ),
        ),
    ),
    "approval_fatigue": (
        (
            "skeleton/security/operator_override.py",
            (
                "def _check_fatigue",
                "approval fatigue bound exceeded",
            ),
        ),
        (
            "skeleton/testing/test_operator_override.py",
            ("test_approval_fatigue_blocks_repeated_operator_actions",),
        ),
    ),
    "undo_recovery": (
        (
            "skeleton/security/operator_override.py",
            (
                "def undo",
                "override undo window expired",
                "override_undone",
            ),
        ),
        (
            "skeleton/testing/test_operator_override.py",
            (
                "test_destructive_recovery_has_one_time_bounded_undo",
                "test_undo_window_expiry_fails_closed",
                "test_non_reversible_action_cannot_fake_undo",
            ),
        ),
    ),
}


class AC19EvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC19EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC19EvidenceError(f"{path} must contain an object")
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


def _anchor(root: Path, relative: str, tokens: tuple[str, ...]) -> dict[str, Any]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise AC19EvidenceError(f"proof anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise AC19EvidenceError(f"proof anchor is not tracked: {relative}")
    text = path.read_text(encoding="utf-8")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise AC19EvidenceError(
            f"{relative} missing required proof tokens: {', '.join(missing)}"
        )
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(tokens),
    }


def build_ac19_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40.fullmatch(expected_head):
        raise AC19EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    adversarial = _load(root / ADVERSARIAL)
    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC19EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (row for row in axes if isinstance(row, dict) and row.get("id") == AXIS_ID),
        None,
    )
    if axis is None:
        raise AC19EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC19EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(
        _load(root / MASTER),
        _load(root / P1_MAP),
        adversarial,
        _load(root / POLICY),
    )
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC19EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    registry = _load(root / REGISTRY)
    records = registry.get("records")
    if not isinstance(records, list):
        raise AC19EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in records
    )

    proofs: dict[str, Any] = {}
    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        anchors = [_anchor(root, path, tokens) for path, tokens in PROOFS[mode]]
        proof = {
            "axis_id": AXIS_ID,
            "mode": mode,
            "expected_head": expected_head,
            "anchors": anchors,
        }
        proof["proof_digest"] = _digest(proof)
        proofs[mode] = proof
        evidence.append(
            {
                "category": mode,
                "digest": proof["proof_digest"],
                "source": (
                    f"p1:adversarial-ac19-evidence:{AXIS_ID}:"
                    f"{mode}:{expected_head}"
                ),
            }
        )

    candidate = {
        "axis_id": AXIS_ID,
        "axis_name": axis.get("name"),
        "obligation_id": obligation.obligation_id,
        "obligation_digest": obligation.obligation_digest,
        "owner_id": OWNER_ID,
        "recommended_severity": "high",
        "recommended_disposition": "evidence",
        "expected_head": expected_head,
        "binding_present": binding_present,
        "required_evidence_modes": list(EXPECTED_MODES),
        "evidence": evidence,
        "proofs": proofs,
        "non_authoritative": True,
        "creates_binding": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
    }
    candidate["candidate_digest"] = _digest(candidate)
    report = {
        "schema_version": 1,
        "engine": "p1-adversarial-ac19-evidence-v1",
        "axis_id": AXIS_ID,
        "expected_head": expected_head,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-candidate", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_ac19_evidence(ROOT, expected_head=args.expected_head)
    except AC19EvidenceError as exc:
        print(f"P1 AC-19 evidence: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_summary:
        print(
            json.dumps(
                {
                    "axis_id": report["axis_id"],
                    "candidate_count": report["candidate_count"],
                    "candidate_binding_count": report["candidate_binding_count"],
                    "expected_head": report["expected_head"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    if args.print_candidate:
        candidate = report["candidate"]
        print(
            "P1_AC19_BINDING_SEED="
            + json.dumps(
                {
                    "obligation_id": candidate["obligation_id"],
                    "obligation_digest": candidate["obligation_digest"],
                    "owner_id": candidate["owner_id"],
                    "severity": candidate["recommended_severity"],
                    "disposition": candidate["recommended_disposition"],
                    "evidence": candidate["evidence"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    print("P1 AC-19 evidence: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
