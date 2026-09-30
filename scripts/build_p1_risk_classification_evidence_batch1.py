#!/usr/bin/env python3
"""Build exact-head evidence candidates for P1 risk classification batch 1.

The verifier is non-authoritative. It proves a bounded set of canonical P1
risk obligations against repository-owned controls and regressions. It does not
write bindings, accept risk, lower severity, or change maturity.
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
CATEGORY = "risk_control_evidence"
BATCH_ID = "p1-risk-classification-evidence-batch1"
RECOMMENDED_SEVERITY = "high"


class RiskClassificationEvidenceError(RuntimeError):
    """Risk classification evidence inputs are malformed or incomplete."""


COVERAGE: dict[tuple[str, str], dict[str, Any]] = {
    ("VOL-000", "human/machine plan divergence"): {
        "sources": [
            "machine/ai_master_plan.json",
            "scripts/check_ai_master_plan.py",
        ],
        "tests": [
            "skeleton/testing/test_ai_master_plan.py",
            "tests/test_p1_maturity_reconciliation.py",
        ],
        "markers": {
            "scripts/check_ai_master_plan.py": [
                "authority must be an object",
                "volume_maturity_policy must be an object",
            ],
            "skeleton/testing/test_ai_master_plan.py": [
                "test_master_plan_machine_contract_is_complete",
                "test_volume_maturity_policy_is_machine_enforced",
            ],
        },
    },
    ("VOL-000", "status inflation without evidence"): {
        "sources": [
            "skeleton/contracts/maturity_reconciliation.py",
            "scripts/reconcile_p1_maturity.py",
            ".github/workflows/p1-maturity-reconciliation.yml",
        ],
        "tests": [
            "skeleton/testing/test_maturity_reconciliation.py",
            "tests/test_p1_maturity_reconciliation.py",
        ],
        "markers": {
            "skeleton/contracts/maturity_reconciliation.py": [
                "accountability evidence is not materialized",
                "highest_eligible_status",
                "promotion_candidate",
            ],
            "tests/test_p1_maturity_reconciliation.py": [
                "test_unsigned_records_never_reach_their_lane_floor",
                "test_live_quality_and_plan_reconciliation_is_blocked_only_by_accountability_before_evidence",
            ],
        },
    },
    ("VOL-000", "parallel planning systems bypassing canonical authority"): {
        "sources": [
            "machine/ai_master_plan.json",
            "scripts/reconcile_p1_maturity.py",
            "scripts/check_ai_scope_freeze.py",
        ],
        "tests": [
            "tests/test_p1_maturity_reconciliation.py",
            "skeleton/testing/test_architecture_scope_freeze.py",
        ],
        "markers": {
            "scripts/reconcile_p1_maturity.py": [
                "master plan authority must be an object",
                "master plan {key} authority pointer drift",
            ],
            "tests/test_p1_maturity_reconciliation.py": [
                "test_reconciliation_rejects_masterplan_authority_pointer_drift",
            ],
            "skeleton/testing/test_architecture_scope_freeze.py": [
                "test_masterplan_authority_pointer_drift_fails_closed",
            ],
        },
    },
    ("VOL-038", "canonicalization mismatch"): {
        "sources": [
            "skeleton/contracts/canonical.py",
            "skeleton/contracts/promotion_evidence.py",
            "scripts/emit_p1_promotion_evidence.py",
        ],
        "tests": [
            "skeleton/testing/test_evidence_ingestion.py",
            "skeleton/testing/test_promotion_evidence.py",
            "tests/test_p1_promotion_evidence_emitter.py",
        ],
        "markers": {
            "skeleton/contracts/canonical.py": [
                "def evidence_ref_identity(",
                "def canonical_payload(self)",
                "def digest(self)",
            ],
            "skeleton/testing/test_promotion_evidence.py": [
                "test_evidence_order_and_duplicates_are_canonicalized",
                "test_subject_changes_when_head_config_or_environment_changes",
            ],
        },
    },
    ("VOL-038", "missing lineage edge"): {
        "sources": [
            "skeleton/contracts/evidence_ingestion.py",
            "skeleton/contracts/promotion_evidence.py",
            ".github/workflows/p1-evidence-identity.yml",
        ],
        "tests": [
            "skeleton/testing/test_evidence_ingestion.py",
            "skeleton/testing/test_promotion_evidence.py",
            "tests/test_p1_promotion_evidence_emitter.py",
        ],
        "markers": {
            "skeleton/contracts/evidence_ingestion.py": [
                "def ingest_execution_evidence(",
                "validated execution evidence",
                "evidence_ids",
            ],
            "skeleton/testing/test_promotion_evidence.py": [
                "test_receipt_binds_exact_subject_and_evidence",
                "test_missing_or_malformed_evidence_fails_closed",
            ],
        },
    },
    ("VOL-038", "signature detached from semantic content"): {
        "sources": [
            "scripts/ai_accountability.py",
            "scripts/check_ai_build_accountability.py",
            "skeleton/contracts/promotion_evidence.py",
            ".github/workflows/p1-evidence-identity.yml",
        ],
        "tests": [
            "tests/test_p1_accountability_materialization.py",
            "skeleton/testing/test_promotion_evidence.py",
        ],
        "markers": {
            "scripts/check_ai_build_accountability.py": [
                "signed {label} needs non-empty evidence_refs",
                "signature method requires signature_ref",
                "signing_required must be true",
            ],
            "skeleton/testing/test_promotion_evidence.py": [
                "test_receipt_binds_exact_subject_and_evidence",
                "test_verifier_and_test_manifest_change_receipt_not_subject",
            ],
        },
    },
    ("VOL-056", "orphan gaps"): {
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
            "scripts/reconcile_p1_risk_evidence.py": [
                "derive_obligations(",
                "bindings reference unknown obligations",
                "duplicate obligation identity",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_inventory_drift_fails_closed",
                "test_unknown_binding_identity_fails_closed",
            ],
        },
    },
    ("VOL-056", "status inflation"): {
        "sources": [
            "skeleton/contracts/maturity_reconciliation.py",
            "scripts/reconcile_p1_maturity.py",
            "skeleton/contracts/risk_evidence.py",
        ],
        "tests": [
            "skeleton/testing/test_ai_master_plan.py",
            "tests/test_p1_maturity_reconciliation.py",
            "skeleton/testing/test_risk_evidence.py",
        ],
        "markers": {
            "skeleton/testing/test_ai_master_plan.py": [
                "test_promoted_volume_without_required_depth_fails_validation",
                "test_closed_gaps_require_hardened_implementation_status",
            ],
            "tests/test_p1_maturity_reconciliation.py": [
                "test_unsigned_records_never_reach_their_lane_floor",
            ],
        },
    },
    ("VOL-056", "duplicate/conflicting records"): {
        "sources": [
            "scripts/check_ai_master_plan.py",
            "scripts/reconcile_p1_risk_evidence.py",
            "skeleton/contracts/risk_evidence.py",
        ],
        "tests": [
            "skeleton/testing/test_ai_master_plan.py",
            "tests/test_p1_risk_evidence_reconciliation.py",
        ],
        "markers": {
            "scripts/reconcile_p1_risk_evidence.py": [
                "duplicate obligation identity",
                "duplicate risk binding",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_duplicate_binding_fails_closed",
                "test_inventory_drift_fails_closed",
            ],
        },
    },
    ("VOL-057", "critical risk hidden by aggregate status"): {
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
                "RiskSeverity.UNCLASSIFIED",
                "classification and binding required",
                "blocking=default_blocking",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_live_p1_risk_inventory_is_deterministic_and_non_authoritative",
                "test_one_real_binding_changes_only_its_own_resolution",
            ],
        },
    },
    ("VOL-057", "stale risk owner"): {
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
                "owner_id: str",
                "binding review is overdue",
                "accepted-risk owner mismatch",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_stale_binding_review_remains_unresolved",
            ],
        },
    },
    ("VOL-057", "paper control without evidence"): {
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
                "evidence disposition requires evidence",
                "risk evidence source must be materialized, not planned",
            ],
            "skeleton/testing/test_risk_evidence.py": [
                "test_materialized_evidence_resolves_high_risk",
                "test_planned_evidence_source_is_rejected",
            ],
        },
    },
}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RiskClassificationEvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise RiskClassificationEvidenceError(f"{path} must contain an object")
    return value


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _validate_paths(root: Path, spec: dict[str, Any]) -> tuple[list[Path], list[Path]]:
    source_paths = [root / item for item in spec["sources"]]
    test_paths = [root / item for item in spec["tests"]]
    for path in source_paths + test_paths:
        if not path.is_file():
            raise RiskClassificationEvidenceError(
                f"evidence path is missing: {path.relative_to(root)}"
            )
    return source_paths, test_paths


def _validate_markers(root: Path, spec: dict[str, Any], volume_key: str) -> None:
    markers = spec.get("markers")
    if not isinstance(markers, dict) or not markers:
        raise RiskClassificationEvidenceError(f"{volume_key}: marker map is empty")
    declared = set(spec["sources"]) | set(spec["tests"])
    for relative, required in markers.items():
        if relative not in declared:
            raise RiskClassificationEvidenceError(
                f"{volume_key}: undeclared marker path: {relative}"
            )
        text = (root / relative).read_text(encoding="utf-8")
        missing = [marker for marker in required if marker not in text]
        if missing:
            raise RiskClassificationEvidenceError(
                f"{volume_key}: {relative} missing contract markers: "
                + ",".join(missing)
            )


def build_risk_classification_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise RiskClassificationEvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    canonical_paths = {
        "master_plan": root / MASTER,
        "p1_execution_map": root / P1_MAP,
        "adversarial_closure": root / ADVERSARIAL,
        "risk_policy": root / POLICY,
        "risk_registry": root / REGISTRY,
    }
    before = {name: _digest_file(path) for name, path in canonical_paths.items()}

    obligations = derive_obligations(
        _load(canonical_paths["master_plan"]),
        _load(canonical_paths["p1_execution_map"]),
        _load(canonical_paths["adversarial_closure"]),
        _load(canonical_paths["risk_policy"]),
    )
    risk_by_identity = {
        (item.source_ref.split(":", 1)[0], item.statement): item
        for item in obligations
        if item.kind is RiskKind.RISK
    }

    registry = _load(canonical_paths["risk_registry"])
    raw_records = registry.get("records")
    if not isinstance(raw_records, list):
        raise RiskClassificationEvidenceError("risk registry records must be a list")
    bound_ids: set[str] = set()
    for index, row in enumerate(raw_records):
        if not isinstance(row, dict):
            raise RiskClassificationEvidenceError(
                f"risk registry record {index} must be an object"
            )
        obligation_id = row.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id:
            raise RiskClassificationEvidenceError(
                f"risk registry record {index} has invalid obligation_id"
            )
        if obligation_id in bound_ids:
            raise RiskClassificationEvidenceError(
                f"duplicate governed binding identity: {obligation_id}"
            )
        bound_ids.add(obligation_id)

    known_ids = {item.obligation_id for item in obligations}
    unknown = sorted(bound_ids - known_ids)
    if unknown:
        raise RiskClassificationEvidenceError(
            "risk registry references unknown obligations: " + ",".join(unknown)
        )

    records: list[dict[str, Any]] = []
    for identity in sorted(COVERAGE):
        volume_key, statement = identity
        obligation = risk_by_identity.get(identity)
        if obligation is None:
            raise RiskClassificationEvidenceError(
                f"missing canonical risk obligation: {volume_key}: {statement}"
            )
        spec = COVERAGE[identity]
        source_paths, test_paths = _validate_paths(root, spec)
        _validate_markers(root, spec, volume_key)

        packet: dict[str, Any] = {
            "batch_id": BATCH_ID,
            "volume_key": volume_key,
            "statement": statement,
            "obligation_id": obligation.obligation_id,
            "obligation_digest": obligation.obligation_digest,
            "source_ref": obligation.source_ref,
            "expected_head": expected_head,
            "recommended_severity": RECOMMENDED_SEVERITY,
            "recommended_disposition": "evidence",
            "source_digests": {
                str(path.relative_to(root)): _digest_file(path)
                for path in source_paths
            },
            "test_digests": {
                str(path.relative_to(root)): _digest_file(path)
                for path in test_paths
            },
            "binding_present": obligation.obligation_id in bound_ids,
            "non_authoritative": True,
            "creates_binding": False,
            "accepts_risk": False,
            "lowers_severity": False,
            "clears_source_risk": False,
            "promotes_maturity": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packet["candidate_evidence_ref"] = {
            "source": (
                f"p1:risk-classification-evidence-batch1:"
                f"{obligation.obligation_id}:{expected_head}"
            ),
            "digest": packet["packet_digest"],
            "category": CATEGORY,
        }
        records.append(packet)

    if len(records) != 12:
        raise RiskClassificationEvidenceError(
            f"expected 12 covered risks, got {len(records)}"
        )
    if len({row["volume_key"] for row in records}) != 4:
        raise RiskClassificationEvidenceError("expected exactly 4 covered volumes")
    if len({row["obligation_id"] for row in records}) != len(records):
        raise RiskClassificationEvidenceError("duplicate covered risk identity")

    after = {name: _digest_file(path) for name, path in canonical_paths.items()}
    if before != after:
        raise RiskClassificationEvidenceError(
            "canonical risk/masterplan sources changed during evidence build"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-risk-classification-evidence-batch1-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "category": CATEGORY,
        "covered_risk_count": len(records),
        "covered_volume_count": len({row["volume_key"] for row in records}),
        "already_bound_count": sum(1 for row in records if row["binding_present"]),
        "candidate_binding_count": sum(1 for row in records if not row["binding_present"]),
        "recommended_severity": RECOMMENDED_SEVERITY,
        "recommended_disposition": "evidence",
        "non_authoritative": True,
        "creates_bindings": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "clears_source_risks": False,
        "promotes_maturity": False,
        "canonical_source_digests": before,
        "records": records,
    }
    report["report_digest"] = _canonical_digest(report)
    return report


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-candidates", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_risk_classification_evidence(
            ROOT,
            expected_head=args.expected_head,
        )
    except RiskClassificationEvidenceError as exc:
        print(f"P1 risk classification evidence: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_render(report), encoding="utf-8")

    if args.print_summary:
        print(json.dumps({
            key: report[key]
            for key in (
                "batch_id",
                "expected_head",
                "covered_risk_count",
                "covered_volume_count",
                "already_bound_count",
                "candidate_binding_count",
                "recommended_severity",
                "recommended_disposition",
                "report_digest",
            )
        }, indent=2, sort_keys=True))

    if args.print_candidates:
        print(json.dumps([
            {
                "volume_key": row["volume_key"],
                "statement": row["statement"],
                "obligation_id": row["obligation_id"],
                "obligation_digest": row["obligation_digest"],
                "recommended_severity": row["recommended_severity"],
                "candidate_evidence_ref": row["candidate_evidence_ref"],
            }
            for row in report["records"]
        ], indent=2, sort_keys=True))

    print(
        "P1 risk classification evidence: OK "
        f"({report['covered_risk_count']} risks across "
        f"{report['covered_volume_count']} volumes; "
        f"{report['candidate_binding_count']} binding candidates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
