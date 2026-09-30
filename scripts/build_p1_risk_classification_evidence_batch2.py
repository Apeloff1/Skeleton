#!/usr/bin/env python3
"""Build exact-head evidence candidates for P1 risk classification batch 2.

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
BATCH_ID = "p1-risk-classification-evidence-batch2"
RECOMMENDED_SEVERITY = "high"


class RiskClassificationEvidenceError(RuntimeError):
    """Risk classification evidence inputs are malformed or incomplete."""


COVERAGE: dict[tuple[str, str], dict[str, Any]] = {
    ("VOL-014", "invalid plans reaching execution"): {
        "sources": [
            "skeleton/intelligence/plan_verifier.py",
            ".github/workflows/p1-plan-verification.yml",
        ],
        "tests": [
            "skeleton/testing/test_plan_qualification.py",
            "skeleton/testing/test_plan_execution_admission.py",
        ],
        "markers": {
            "skeleton/intelligence/plan_verifier.py": [
                "def admit_plan_execution(",
                "def require_privileged_execution_admission(",
                "plan-qualification-rejected",
            ],
            "skeleton/testing/test_plan_qualification.py": [
                "test_rejected_static_or_simulation_result_cannot_qualify",
                "test_rejected_plan_cannot_admit_privileged_execution",
            ],
            "skeleton/testing/test_plan_execution_admission.py": [
                "test_rejected_plan_cannot_gain_privileged_admission",
                "test_privileged_step_requires_exact_qualified_admission",
            ],
        },
    },
    ("VOL-014", "goal drift"): {
        "sources": [
            "skeleton/intelligence/plan_verifier.py",
            ".github/workflows/p1-plan-verification.yml",
        ],
        "tests": [
            "skeleton/testing/test_plan_simulation.py",
            "skeleton/testing/test_plan_qualification.py",
            "skeleton/testing/test_plan_execution_admission.py",
        ],
        "markers": {
            "skeleton/intelligence/plan_verifier.py": [
                "reasoning-policy-digest-mismatch",
                "planning-history-digest-mismatch",
                "analysis-plan-digest-mismatch",
            ],
            "skeleton/testing/test_plan_simulation.py": [
                "test_stale_analysis_digest_is_rejected",
            ],
            "skeleton/testing/test_plan_qualification.py": [
                "test_intel03_policy_and_history_are_cryptographically_bound",
            ],
            "skeleton/testing/test_plan_execution_admission.py": [
                "test_stale_plan_digest_cannot_reuse_admission",
            ],
        },
    },
    ("VOL-014", "scheduler optimization violating hard constraints"): {
        "sources": [
            "skeleton/intelligence/plan_verifier.py",
            ".github/workflows/p1-plan-verification.yml",
        ],
        "tests": [
            "skeleton/testing/test_plan_static_analyzer.py",
            "skeleton/testing/test_plan_simulation.py",
            "skeleton/testing/test_plan_qualification.py",
        ],
        "markers": {
            "skeleton/testing/test_plan_static_analyzer.py": [
                "test_capability_and_budget_overreach_fail_closed",
                "test_irreversible_steps_require_explicit_policy_allowance",
            ],
            "skeleton/testing/test_plan_simulation.py": [
                "test_runtime_capability_drift_blocks_even_after_static_acceptance",
            ],
            "skeleton/testing/test_plan_qualification.py": [
                "test_under_specified_privileged_step_fails_admission",
            ],
        },
    },
    ("VOL-040", "cursor compaction gap"): {
        "sources": [
            "backend/core/operation_stream_transport.py",
            "backend/routes/operation_stream.py",
        ],
        "tests": [
            "backend/tests/test_operation_stream_transport.py",
            "backend/tests/test_operation_stream_route.py",
        ],
        "markers": {
            "backend/core/operation_stream_transport.py": [
                "def resync_snapshot(",
                "def compact_acknowledged(",
                "compact only history acknowledged by every active consumer",
            ],
            "backend/tests/test_operation_stream_transport.py": [
                "test_transport_replay_preserves_explicit_compaction_gap",
                "test_resync_snapshot_returns_compaction_floor_and_latest_cursor",
            ],
            "backend/tests/test_operation_stream_route.py": [
                "test_json_replay_maps_compaction_gap_to_resync_conflict",
                "test_ack_route_compacts_only_after_active_consumers_apply",
            ],
        },
    },
    ("VOL-040", "duplicate provisional content"): {
        "sources": [
            "backend/core/operation_projection.py",
            "skeleton/frontier/operation_stream.py",
        ],
        "tests": [
            "backend/tests/test_operation_projection.py",
            "skeleton/testing/test_operation_stream.py",
        ],
        "markers": {
            "backend/core/operation_projection.py": [
                "exact duplicate deliveries are idempotent",
                "unknown/conflicting duplicates require resync or fail closed",
            ],
            "backend/tests/test_operation_projection.py": [
                "test_exact_duplicate_delivery_is_idempotent",
                "test_conflicting_duplicate_sequence_fails_closed",
            ],
            "skeleton/testing/test_operation_stream.py": [
                "test_stream_duplicate_event_id_is_idempotent_only_for_identical_event",
            ],
        },
    },
    ("VOL-040", "cancel/complete race"): {
        "sources": [
            "backend/core/operation_stream_transport.py",
            "backend/core/operation_projection.py",
        ],
        "tests": [
            "backend/tests/test_operation_stream_transport.py",
            "backend/tests/test_operation_projection.py",
            "skeleton/testing/test_operation_stream.py",
        ],
        "markers": {
            "backend/core/operation_stream_transport.py": [
                "Cancel the canonical operation, idempotently across terminal races.",
                "operation changed during cancellation",
            ],
            "backend/tests/test_operation_stream_transport.py": [
                "test_cancel_complete_race_preserves_single_completed_terminal",
            ],
            "backend/tests/test_operation_projection.py": [
                "test_terminal_projection_cannot_advance_to_another_state",
            ],
            "skeleton/testing/test_operation_stream.py": [
                "test_stream_terminal_event_prevents_future_writes",
            ],
        },
    },
    ("VOL-041", "version drift"): {
        "sources": [
            "backend/core/api_contract_registry.py",
            "machine/p1_api_contract_registry.json",
            "scripts/check_p1_api_contract_registry.py",
        ],
        "tests": [
            "backend/tests/test_api_contract_registry.py",
            "tests/test_p1_api_contract_registry.py",
        ],
        "markers": {
            "backend/core/api_contract_registry.py": [
                "version-regressed",
                "changed-without-version-advance",
                "missing-migration-rule",
            ],
            "backend/tests/test_api_contract_registry.py": [
                "test_unversioned_schema_change_fails_closed",
                "test_schema_change_requires_versioned_migration",
            ],
            "tests/test_p1_api_contract_registry.py": [
                "test_schema_drift_without_migration_is_rejected",
                "test_stale_path_fails_closed",
            ],
        },
    },
    ("VOL-041", "ambiguous retry duplicates mutation"): {
        "sources": [
            "backend/core/api_contract_registry.py",
            "backend/core/product_operations.py",
        ],
        "tests": [
            "backend/tests/test_api_contract_registry.py",
            "backend/tests/test_product_operations.py",
        ],
        "markers": {
            "backend/core/api_contract_registry.py": [
                "idempotent: bool",
                "idempotency-semantics-changed",
            ],
            "backend/core/product_operations.py": [
                "idempotent retries",
                "idempotency index is refreshed",
                "if idempotency_key is not None and idempotency_key in self._idempotency",
            ],
            "backend/tests/test_product_operations.py": [
                "test_idempotency_key_returns_original_operation_without_duplicate_work",
                "test_two_coordinators_share_idempotency_index_under_process_lease",
            ],
        },
    },
    ("VOL-041", "UI-specific fields leak into core contracts"): {
        "sources": [
            "backend/core/api_contract_registry.py",
            "machine/p1_api_contract_registry.json",
        ],
        "tests": [
            "backend/tests/test_api_contract_registry.py",
            "tests/test_p1_api_contract_registry.py",
        ],
        "markers": {
            "backend/core/api_contract_registry.py": [
                "consumers: tuple[str, ...]",
                "authority-semantics-changed",
                "consumer-removed",
            ],
            "backend/tests/test_api_contract_registry.py": [
                "test_authority_and_consumer_semantics_are_absolute_breaks",
            ],
            "tests/test_p1_api_contract_registry.py": [
                "test_route_source_drift_is_detected_independently_of_registry",
                "test_machine_router_prefix_cannot_drift_from_source",
            ],
        },
    },
    ("VOL-042", "UI becomes authoritative"): {
        "sources": [
            "backend/core/product_shell_projection.py",
            "backend/core/operation_projection.py",
        ],
        "tests": [
            "backend/tests/test_product_shell_projection.py",
            "backend/tests/test_operation_projection.py",
        ],
        "markers": {
            "backend/core/product_shell_projection.py": [
                "product projection is read-only",
                "verify_projection_authority(",
                "operation projection does not match durable authority",
            ],
            "backend/tests/test_product_shell_projection.py": [
                "test_projection_is_read_only_and_bound_to_durable_authority",
            ],
            "backend/tests/test_operation_projection.py": [
                "test_authority_tenant_or_identity_drift_is_rejected",
            ],
        },
    },
    ("VOL-042", "stale optimistic state"): {
        "sources": [
            "backend/core/product_shell_projection.py",
            "backend/core/operation_projection.py",
        ],
        "tests": [
            "backend/tests/test_product_shell_projection.py",
            "backend/tests/test_operation_projection.py",
        ],
        "markers": {
            "backend/tests/test_product_shell_projection.py": [
                "test_event_outside_receipt_window_is_not_trusted",
                "test_stale_or_cross_tenant_projection_cannot_overwrite_authority",
            ],
            "backend/tests/test_operation_projection.py": [
                "test_operation_version_drift_requires_resync",
                "test_out_of_order_gap_requires_resync",
            ],
        },
    },
    ("VOL-042", "hidden degraded capability"): {
        "sources": [
            "backend/core/product_shell_projection.py",
            "backend/core/operation_projection.py",
        ],
        "tests": [
            "backend/tests/test_product_shell_projection.py",
            "backend/tests/test_operation_projection.py",
        ],
        "markers": {
            "backend/core/product_shell_projection.py": [
                "_STATE_BLOCKERS",
                "Retry policy is active.",
                "terminal_result",
            ],
            "backend/tests/test_product_shell_projection.py": [
                "test_waiting_state_derives_blocker_without_inventing_external_reason",
                "test_terminal_failure_never_projects_final_output_digest",
            ],
            "backend/tests/test_operation_projection.py": [
                "test_illegal_state_transition_is_never_projected",
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
        "engine": "p1-risk-classification-evidence-batch2-v1",
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
