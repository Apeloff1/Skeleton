#!/usr/bin/env python3
"""Build exact-head evidence for AC-10 key continuity and AC-21 recovery bootstrap."""

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

AXES = ("AC-10", "AC-21")
OWNER_ID = "ACC-P1-EVID-04"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

PROOFS: dict[str, dict[str, tuple[tuple[str, tuple[str, ...]], ...]]] = {
    "AC-10": {
        "credential_rotation": (
            (
                "skeleton/kernel/keyholder.py",
                (
                    "class KeyRotationReceipt",
                    "def rotate",
                    "rotation key already exists in continuity history",
                ),
            ),
            (
                "skeleton/testing/test_keyholder.py",
                (
                    "test_key_continuity_rotation_preserves_non_revoked_historical_verification",
                    "test_rotation_rejects_reusing_existing_identity",
                ),
            ),
        ),
        "revocation_replay": (
            (
                "skeleton/kernel/keyholder.py",
                (
                    "def revoke",
                    "active key must be rotated before revocation",
                    "KeyRevokedError",
                ),
            ),
            (
                "skeleton/testing/test_keyholder.py",
                (
                    "test_rotation_with_revocation_rejects_old_key_now_but_preserves_history",
                    "test_explicit_revocation_advances_generation_and_is_idempotent",
                    "test_active_key_cannot_be_revoked_without_rotation",
                ),
            ),
        ),
        "identity_restore": (
            (
                "skeleton/kernel/keyholder.py",
                (
                    "def snapshot",
                    "def restore",
                    "missing seed for retained key identity",
                    "restored seed does not match key identity",
                ),
            ),
            (
                "skeleton/testing/test_keyholder.py",
                (
                    "test_key_continuity_snapshot_restore_preserves_identity_without_exporting_seeds",
                    "test_key_continuity_restore_rejects_wrong_or_missing_seed",
                ),
            ),
        ),
        "historical_signature_verify": (
            (
                "skeleton/kernel/keyholder.py",
                (
                    "def verify_historical",
                    "signature postdates requested generation",
                    "key was revoked at requested generation",
                ),
            ),
            (
                "skeleton/testing/test_keyholder.py",
                (
                    "test_rotation_with_revocation_rejects_old_key_now_but_preserves_history",
                    "test_historical_verification_rejects_signature_from_future_generation",
                ),
            ),
        ),
    },
    "AC-21": {
        "recovery_dependency_graph": (
            (
                "skeleton/resilience/recovery_bootstrap.py",
                (
                    "class RecoveryDependencyGraph",
                    "def topological_order",
                    "recovery dependency cycle detected",
                ),
            ),
            (
                "skeleton/testing/test_recovery_bootstrap.py",
                (
                    "test_default_graph_is_acyclic_and_dependency_first",
                    "test_dependency_cycle_fails_at_graph_construction",
                ),
            ),
        ),
        "safe_mode_drill": (
            (
                "skeleton/resilience/recovery_bootstrap.py",
                (
                    "def dependency_reduced_order",
                    "no safe-mode recovery nodes survive",
                    "safe mode depends on unavailable/non-safe nodes",
                ),
            ),
            (
                "skeleton/testing/test_recovery_bootstrap.py",
                (
                    "test_default_safe_mode_excludes_normal_control_planes",
                    "test_safe_mode_rejects_hidden_dependency_on_normal_scheduler",
                    "test_safe_mode_requires_at_least_one_survivor",
                ),
            ),
        ),
        "control_plane_isolation": (
            (
                "skeleton/resilience/recovery_bootstrap.py",
                (
                    "DEFAULT_UNAVAILABLE_CONTROL_PLANES",
                    "normal_scheduler",
                    "normal_queue",
                    "telemetry",
                ),
            ),
            (
                "skeleton/testing/test_recovery_bootstrap.py",
                (
                    "assert set(order).isdisjoint(DEFAULT_UNAVAILABLE_CONTROL_PLANES)",
                    "test_unknown_unavailable_dependency_is_rejected",
                ),
            ),
        ),
        "cold_restore": (
            (
                "skeleton/resilience/recovery_bootstrap.py",
                (
                    "def cold_restore_order",
                    "cold restore dependency order invalid",
                    "cold restore order values must be unique",
                ),
            ),
            (
                "skeleton/testing/test_recovery_bootstrap.py",
                (
                    "test_cold_restore_order_is_explicit_and_dependency_safe",
                    "test_cold_restore_rejects_dependency_inversion",
                ),
            ),
        ),
    },
}


class EvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{path} must contain an object")
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
        raise EvidenceError(f"proof anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise EvidenceError(f"proof anchor is not tracked: {relative}")
    text = path.read_text(encoding="utf-8")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise EvidenceError(
            f"{relative} missing required proof tokens: {', '.join(missing)}"
        )
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(tokens),
    }


def build_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40.fullmatch(expected_head):
        raise EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    adversarial = _load(root / ADVERSARIAL)
    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise EvidenceError("adversarial closure axes must be a list")
    axis_by_id = {
        row["id"]: row
        for row in axes
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    obligations = derive_obligations(
        _load(root / MASTER),
        _load(root / P1_MAP),
        adversarial,
        _load(root / POLICY),
    )
    obligation_by_axis = {
        item.source_ref: item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL
    }
    registry = _load(root / REGISTRY)
    records = registry.get("records")
    if not isinstance(records, list):
        raise EvidenceError("risk registry records must be a list")
    bound_ids = {
        row.get("obligation_id")
        for row in records
        if isinstance(row, dict)
    }

    candidates: list[dict[str, Any]] = []
    for axis_id in AXES:
        axis = axis_by_id.get(axis_id)
        obligation = obligation_by_axis.get(axis_id)
        if axis is None or obligation is None:
            raise EvidenceError(f"{axis_id} canonical obligation is missing")
        expected_modes = tuple(PROOFS[axis_id])
        if tuple(axis.get("required_evidence_modes") or ()) != expected_modes:
            raise EvidenceError(f"{axis_id} evidence modes drifted")

        proofs: dict[str, Any] = {}
        evidence: list[dict[str, str]] = []
        for mode in expected_modes:
            anchors = [
                _anchor(root, path, tokens)
                for path, tokens in PROOFS[axis_id][mode]
            ]
            proof = {
                "axis_id": axis_id,
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
                        f"p1:adversarial-ac10-ac21-evidence:{axis_id}:"
                        f"{mode}:{expected_head}"
                    ),
                }
            )

        binding_present = obligation.obligation_id in bound_ids
        candidate = {
            "axis_id": axis_id,
            "axis_name": axis.get("name"),
            "obligation_id": obligation.obligation_id,
            "obligation_digest": obligation.obligation_digest,
            "owner_id": OWNER_ID,
            "recommended_severity": "high",
            "recommended_disposition": "evidence",
            "expected_head": expected_head,
            "binding_present": binding_present,
            "required_evidence_modes": list(expected_modes),
            "evidence": evidence,
            "proofs": proofs,
            "non_authoritative": True,
            "creates_binding": False,
            "accepts_risk": False,
            "lowers_severity": False,
            "promotes_maturity": False,
        }
        candidate["candidate_digest"] = _digest(candidate)
        candidates.append(candidate)

    report = {
        "schema_version": 1,
        "engine": "p1-adversarial-ac10-ac21-evidence-v1",
        "axis_ids": list(AXES),
        "axis_count": len(AXES),
        "expected_head": expected_head,
        "already_bound_count": sum(
            int(row["binding_present"]) for row in candidates
        ),
        "candidate_binding_count": sum(
            int(not row["binding_present"]) for row in candidates
        ),
        "non_authoritative": True,
        "creates_bindings": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
        "candidates": candidates,
    }
    report["report_digest"] = _digest(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-candidates", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_evidence(ROOT, expected_head=args.expected_head)
    except EvidenceError as exc:
        print(f"P1 AC-10/AC-21 evidence: rejected: {exc}", file=sys.stderr)
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
                    "axis_ids": report["axis_ids"],
                    "already_bound_count": report["already_bound_count"],
                    "candidate_binding_count": report["candidate_binding_count"],
                    "expected_head": report["expected_head"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    if args.print_candidates:
        payload = [
            {
                "axis_id": row["axis_id"],
                "obligation_id": row["obligation_id"],
                "obligation_digest": row["obligation_digest"],
                "owner_id": row["owner_id"],
                "severity": row["recommended_severity"],
                "disposition": row["recommended_disposition"],
                "evidence": row["evidence"],
            }
            for row in report["candidates"]
        ]
        print(
            "P1_AC10_AC21_BINDING_SEEDS="
            + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )
    print("P1 AC-10/AC-21 evidence: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
