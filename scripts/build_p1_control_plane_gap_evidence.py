#!/usr/bin/env python3
"""Build exact-head evidence candidates for P1 control-plane gap batch 2.

This verifier is deliberately non-authoritative. It proves a bounded set of
canonical P1 gaps against repository-owned contracts, policy registries,
workflows, and regression tests. It never writes EVID-04 bindings, clears
masterplan gaps, signs accountability, or changes maturity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
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
CATEGORY = "control_plane_gap_closure"
BATCH_ID = "p1-control-plane-gap-batch2"


class ControlPlaneGapEvidenceError(RuntimeError):
    """Control-plane gap evidence inputs are malformed or incomplete."""


COVERAGE: dict[tuple[str, str], dict[str, Any]] = {
    (
        "VOL-056",
        "establish canonical gap schema",
    ): {
        "sources": [
            "skeleton/contracts/risk_evidence.py",
            "scripts/reconcile_p1_risk_evidence.py",
            "machine/p1_risk_evidence_policy.json",
        ],
        "tests": [
            "skeleton/testing/test_risk_evidence.py",
            "tests/test_p1_risk_evidence_reconciliation.py",
        ],
        "markers": {
            "skeleton/contracts/risk_evidence.py": [
                "class RiskObligation:",
                "def make_obligation_id(",
                "class RiskKind(str, Enum):",
            ],
            "scripts/reconcile_p1_risk_evidence.py": [
                '_source_rule(policy, "volume_gap")',
                "derive_obligations(",
                '"obligation_digest": obligation.obligation_digest',
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_inventory_drift_fails_closed",
                "test_unknown_binding_identity_fails_closed",
            ],
        },
    },
    (
        "VOL-056",
        "bind CI to unresolved blocking gaps",
    ): {
        "sources": [
            "scripts/reconcile_p1_risk_evidence.py",
            ".github/workflows/p1-risk-evidence-binding.yml",
        ],
        "tests": [
            "tests/test_p1_risk_evidence_reconciliation.py",
        ],
        "markers": {
            "scripts/reconcile_p1_risk_evidence.py": [
                '"unresolved_blocking_count"',
                '--require-resolved',
                "unresolved blocking obligations",
            ],
            ".github/workflows/p1-risk-evidence-binding.yml": [
                "Prove strict terminal mode fails closed while work is unresolved",
                "--require-resolved",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                'assert report["unresolved_blocking_count"] == 479',
            ],
        },
    },
    (
        "VOL-057",
        "bind risks to work/evidence graph",
    ): {
        "sources": [
            "skeleton/contracts/risk_evidence.py",
            "scripts/reconcile_p1_risk_evidence.py",
            "machine/p1_risk_evidence_bindings.json",
        ],
        "tests": [
            "skeleton/testing/test_risk_evidence.py",
            "tests/test_p1_risk_evidence_reconciliation.py",
        ],
        "markers": {
            "skeleton/contracts/risk_evidence.py": [
                "class RiskEvidenceBinding:",
                "owner_id: str",
                "evidence: tuple[EvidenceRef, ...]",
            ],
            "scripts/reconcile_p1_risk_evidence.py": [
                "bindings: dict[str, RiskEvidenceBinding]",
                "obligation_by_id",
                "evaluate_risk_binding(",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_one_real_binding_changes_only_its_own_resolution",
            ],
        },
    },
    (
        "VOL-057",
        "materialize expiry/review cadence",
    ): {
        "sources": [
            "skeleton/contracts/risk_evidence.py",
            "scripts/reconcile_p1_risk_evidence.py",
        ],
        "tests": [
            "skeleton/testing/test_risk_evidence.py",
            "tests/test_p1_risk_evidence_reconciliation.py",
        ],
        "markers": {
            "skeleton/contracts/risk_evidence.py": [
                "review_at: datetime",
                "expires_at: datetime",
                "def valid_at(",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_stale_binding_review_remains_unresolved",
                "binding review is overdue",
            ],
        },
    },
    (
        "VOL-059",
        "define required-gate authority map",
    ): {
        "sources": [
            "machine/p1_required_gate_authority.json",
            "skeleton/contracts/promotion_gates.py",
            "scripts/check_p1_required_gate_authority.py",
        ],
        "tests": [
            "tests/test_p1_required_gate_authority.py",
            "skeleton/testing/test_promotion_gates.py",
        ],
        "markers": {
            "machine/p1_required_gate_authority.json": [
                '"policy_id": "skeleton.p1.required_gate_authority"',
                '"required_gate_count": 26',
                '"all_required_gates_must_pass": true',
            ],
            "skeleton/contracts/promotion_gates.py": [
                "def evaluate_required_gates(",
                "required_gate_count=len(required)",
            ],
            "tests/test_p1_required_gate_authority.py": [
                "test_repository_required_gate_authority_is_valid",
                'assert summary["required_gate_count"] == 26',
            ],
        },
    },
    (
        "VOL-059",
        "add cancellation/skip fail-closed tests",
    ): {
        "sources": [
            "machine/p1_required_gate_authority.json",
            "skeleton/contracts/promotion_gates.py",
        ],
        "tests": [
            "tests/test_p1_required_gate_authority.py",
            "skeleton/testing/test_promotion_gates.py",
        ],
        "markers": {
            "machine/p1_required_gate_authority.json": [
                '"skipped_conclusion": "reject"',
                '"cancelled_conclusion": "reject"',
            ],
            "skeleton/testing/test_promotion_gates.py": [
                '("completed", "cancelled", "rejected")',
                '("completed", "skipped", "rejected")',
                "test_missing_required_gate_fails_closed",
            ],
            "tests/test_p1_required_gate_authority.py": [
                "test_authority_rejects_fail_closed_policy_drift",
            ],
        },
    },
    (
        "VOL-078",
        "define replay bundle format",
    ): {
        "sources": [
            "skeleton/contracts/reproducibility.py",
            "machine/p1_reproducibility_policy.json",
            "scripts/check_p1_reproducibility.py",
        ],
        "tests": [
            "skeleton/testing/test_reproducibility.py",
            "tests/test_p1_reproducibility_bundle.py",
        ],
        "markers": {
            "skeleton/contracts/reproducibility.py": [
                'REPRODUCIBILITY_SCHEMA_ID = "skeleton.p1.reproducibility_bundle"',
                "class ReproducibilityBundle:",
                "def bundle_digest(",
            ],
            "tests/test_p1_reproducibility_bundle.py": [
                "test_bundle_loader_rejects_tampered_digest",
            ],
        },
    },
    (
        "VOL-078",
        "bind qualifying evidence to replay verification",
    ): {
        "sources": [
            "skeleton/contracts/reproducibility.py",
            "scripts/check_p1_reproducibility.py",
            ".github/workflows/p1-reproducibility-bundle.yml",
        ],
        "tests": [
            "skeleton/testing/test_reproducibility.py",
            "tests/test_p1_reproducibility_bundle.py",
        ],
        "markers": {
            "skeleton/contracts/reproducibility.py": [
                "def bundle_from_receipt(",
                "def evaluate_replay(",
                "expected_evidence_digest=receipt.evidence_digest",
                "ReplayDisposition.REPRODUCED",
            ],
            "tests/test_p1_reproducibility_bundle.py": [
                "test_verify_returns_nonzero_with_deterministic_incompatibility",
            ],
        },
    },
    (
        "VOL-420",
        "enforce freeze in validator",
    ): {
        "sources": [
            "scripts/check_ai_scope_freeze.py",
            "machine/ai_scope_freeze_adrs.json",
            ".github/workflows/p1-scope-freeze.yml",
        ],
        "tests": [
            "skeleton/testing/test_architecture_scope_freeze.py",
        ],
        "markers": {
            "scripts/check_ai_scope_freeze.py": [
                "breadth freeze must remain enabled",
                "active P1 scope requires exactly",
                "unapproved top-level volume exceeds active P1 breadth freeze",
            ],
            "skeleton/testing/test_architecture_scope_freeze.py": [
                "test_direct_top_level_volume_insertion_fails_closed",
                "test_breadth_freeze_application_policy_cannot_be_weakened",
            ],
        },
    },
    (
        "VOL-420",
        "maintain ADR exception workflow",
    ): {
        "sources": [
            "scripts/check_ai_scope_freeze.py",
            "machine/ai_scope_freeze_adrs.json",
        ],
        "tests": [
            "skeleton/testing/test_architecture_scope_freeze.py",
        ],
        "markers": {
            "machine/ai_scope_freeze_adrs.json": [
                '"approved_future"',
                '"architecture_owner"',
                '"independent_verifier"',
                '"distinct_signers_required": true',
            ],
            "scripts/check_ai_scope_freeze.py": [
                "scope-freeze ADR id must match ADR-SCOPE-NNNN",
                "approved ADR requires decision_summary",
                "applied scope expansion is forbidden during active P1",
            ],
            "skeleton/testing/test_architecture_scope_freeze.py": [
                "test_approved_future_adr_requires_identity_bound_approvals",
                "test_valid_approved_future_adr_still_does_not_expand_p1",
                "test_applied_adr_is_rejected_during_active_p1",
            ],
        },
    },
}


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlPlaneGapEvidenceError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise ControlPlaneGapEvidenceError(f"{path} must contain an object")
    return payload


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return _digest_bytes(raw)


def _validate_spec_paths(root: Path, spec: dict[str, Any]) -> tuple[list[Path], list[Path]]:
    source_paths = [root / item for item in spec["sources"]]
    test_paths = [root / item for item in spec["tests"]]
    for path in source_paths + test_paths:
        if not path.is_file():
            raise ControlPlaneGapEvidenceError(
                f"evidence path is missing: {path.relative_to(root)}"
            )
    return source_paths, test_paths


def _validate_markers(root: Path, spec: dict[str, Any], volume_key: str) -> None:
    markers = spec.get("markers")
    if not isinstance(markers, dict) or not markers:
        raise ControlPlaneGapEvidenceError(f"{volume_key}: marker map is empty")
    declared = set(spec["sources"]) | set(spec["tests"])
    for relative, required in markers.items():
        if relative not in declared:
            raise ControlPlaneGapEvidenceError(
                f"{volume_key}: marker path is not declared evidence: {relative}"
            )
        if not isinstance(required, list) or not required:
            raise ControlPlaneGapEvidenceError(
                f"{volume_key}: marker list is empty for {relative}"
            )
        text = (root / relative).read_text(encoding="utf-8")
        missing = [marker for marker in required if marker not in text]
        if missing:
            raise ControlPlaneGapEvidenceError(
                f"{volume_key}: {relative} missing contract markers: "
                + ",".join(missing)
            )


def build_control_plane_gap_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise ControlPlaneGapEvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    canonical_paths = {
        "master_plan": root / MASTER,
        "p1_execution_map": root / P1_MAP,
        "adversarial_closure": root / ADVERSARIAL,
        "risk_policy": root / POLICY,
        "risk_registry": root / REGISTRY,
    }
    before = {
        name: _digest_file(path)
        for name, path in canonical_paths.items()
    }

    master = _load(canonical_paths["master_plan"])
    p1_map = _load(canonical_paths["p1_execution_map"])
    adversarial = _load(canonical_paths["adversarial_closure"])
    policy = _load(canonical_paths["risk_policy"])
    registry = _load(canonical_paths["risk_registry"])

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    gap_by_identity = {
        (
            obligation.source_ref.split(":", 1)[0],
            obligation.statement,
        ): obligation
        for obligation in obligations
        if obligation.kind is RiskKind.GAP
    }

    registry_rows = registry.get("records")
    if not isinstance(registry_rows, list):
        raise ControlPlaneGapEvidenceError("risk registry records must be a list")
    bound_ids: set[str] = set()
    for index, row in enumerate(registry_rows):
        if not isinstance(row, dict):
            raise ControlPlaneGapEvidenceError(
                f"risk registry record {index} must be an object"
            )
        obligation_id = row.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id:
            raise ControlPlaneGapEvidenceError(
                f"risk registry record {index} has invalid obligation_id"
            )
        if obligation_id in bound_ids:
            raise ControlPlaneGapEvidenceError(
                f"duplicate governed binding identity: {obligation_id}"
            )
        bound_ids.add(obligation_id)

    known_ids = {item.obligation_id for item in obligations}
    unknown_ids = sorted(bound_ids - known_ids)
    if unknown_ids:
        raise ControlPlaneGapEvidenceError(
            "risk registry references unknown obligations: "
            + ",".join(unknown_ids)
        )

    records: list[dict[str, Any]] = []
    for identity in sorted(COVERAGE):
        volume_key, statement = identity
        obligation = gap_by_identity.get(identity)
        if obligation is None:
            raise ControlPlaneGapEvidenceError(
                f"missing canonical gap obligation: {volume_key}: {statement}"
            )
        spec = COVERAGE[identity]
        source_paths, test_paths = _validate_spec_paths(root, spec)
        _validate_markers(root, spec, volume_key)

        packet: dict[str, Any] = {
            "batch_id": BATCH_ID,
            "volume_key": volume_key,
            "statement": statement,
            "obligation_id": obligation.obligation_id,
            "obligation_digest": obligation.obligation_digest,
            "source_ref": obligation.source_ref,
            "expected_head": expected_head,
            "source_digests": {
                str(path.relative_to(root)): _digest_file(path)
                for path in source_paths
            },
            "test_digests": {
                str(path.relative_to(root)): _digest_file(path)
                for path in test_paths
            },
            "verified_contract_markers": {
                path: list(markers)
                for path, markers in sorted(spec["markers"].items())
            },
            "binding_present": obligation.obligation_id in bound_ids,
            "non_authoritative": True,
            "creates_binding": False,
            "clears_masterplan_gap": False,
            "signs_accountability": False,
            "promotes_maturity": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packet["candidate_evidence_ref"] = {
            "source": (
                f"p1:control-plane-gap-batch2:"
                f"{obligation.obligation_id}:{expected_head}"
            ),
            "digest": packet["packet_digest"],
            "category": CATEGORY,
        }
        records.append(packet)

    ids = [row["obligation_id"] for row in records]
    if len(ids) != len(set(ids)):
        raise ControlPlaneGapEvidenceError("duplicate covered obligation identity")
    if len(records) != 10:
        raise ControlPlaneGapEvidenceError(
            f"expected 10 covered gaps, got {len(records)}"
        )

    after = {
        name: _digest_file(path)
        for name, path in canonical_paths.items()
    }
    if before != after:
        raise ControlPlaneGapEvidenceError(
            "canonical risk/masterplan sources changed during evidence build"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-control-plane-gap-evidence-batch2-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "category": CATEGORY,
        "covered_gap_count": len(records),
        "covered_volume_count": len(
            {row["volume_key"] for row in records}
        ),
        "already_bound_count": sum(
            1 for row in records if row["binding_present"]
        ),
        "candidate_binding_count": sum(
            1 for row in records if not row["binding_present"]
        ),
        "non_authoritative": True,
        "creates_bindings": False,
        "clears_masterplan_gaps": False,
        "signs_accountability": False,
        "promotes_maturity": False,
        "canonical_source_digests": before,
        "records": records,
    }
    report["report_digest"] = _canonical_digest(report)
    return report


def _canonical_text(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-candidates", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_control_plane_gap_evidence(
            ROOT,
            expected_head=args.expected_head,
        )
    except ControlPlaneGapEvidenceError as exc:
        print(
            f"P1 control-plane gap evidence: rejected: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_canonical_text(report), encoding="utf-8")

    if args.print_summary:
        print(
            json.dumps(
                {
                    "batch_id": report["batch_id"],
                    "expected_head": report["expected_head"],
                    "covered_gap_count": report["covered_gap_count"],
                    "covered_volume_count": report["covered_volume_count"],
                    "already_bound_count": report["already_bound_count"],
                    "candidate_binding_count": report["candidate_binding_count"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )

    if args.print_candidates:
        print(
            json.dumps(
                [
                    {
                        "volume_key": row["volume_key"],
                        "statement": row["statement"],
                        "obligation_id": row["obligation_id"],
                        "obligation_digest": row["obligation_digest"],
                        "candidate_evidence_ref": row["candidate_evidence_ref"],
                    }
                    for row in report["records"]
                ],
                indent=2,
                sort_keys=True,
            )
        )

    print(
        "P1 control-plane gap evidence: OK "
        f"({report['covered_gap_count']} gaps across "
        f"{report['covered_volume_count']} volumes; "
        f"{report['candidate_binding_count']} binding candidates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
