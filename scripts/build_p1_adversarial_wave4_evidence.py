#!/usr/bin/env python3
"""Build exact-head evidence for the P1 adversarial wave-4 axes."""

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
BATCH_ID = "p1-adversarial-wave4-evidence"
OWNER_ID = "ACC-P1-EVID-04"
AXES = ("AC-01", "AC-03", "AC-07", "AC-08")

MODES: dict[str, tuple[str, ...]] = {
    "AC-01": (
        "clean_machine_e2e",
        "trust_root_rotation",
        "bootstrap_fault_injection",
        "recovery_drill",
    ),
    "AC-03": (
        "resource_exhaustion",
        "load_test",
        "soak",
        "degraded_mode",
    ),
    "AC-07": (
        "mixed_version",
        "upgrade_downgrade",
        "schema_compatibility",
        "rollback_rehearsal",
    ),
    "AC-08": (
        "restore_drill",
        "tombstone_propagation",
        "external_reconciliation",
        "credential_revalidation",
    ),
}

ProofEntry = tuple[str, tuple[str, ...]]
PROOFS: dict[str, dict[str, tuple[ProofEntry, ...]]] = {
    "AC-01": {
        "clean_machine_e2e": (
            (
                "skeleton/testing/test_app_bootstrap.py",
                (
                    "test_public_bootstrap_is_dependency_closed_and_sanitized",
                    "test_three_layer_bootstrap_contract_is_wired",
                    "test_aggregate_runtime_status_includes_engine_and_state",
                ),
            ),
            (
                "backend/core/system_root_attestation.py",
                (
                    "def build_root_attestation",
                    "def verify_root_attestation",
                ),
            ),
        ),
        "trust_root_rotation": (
            (
                "backend/tests/test_deployment_checkpoint_policy_rotation.py",
                (
                    "test_dual_quorum_rotation_advances_pinned_policy_identity",
                    "test_rotation_requires_exact_old_pin_and_new_key_registry",
                    "test_rotation_approvals_expire_under_manifest_freshness",
                ),
            ),
            (
                "backend/tests/test_deployment_checkpoint_trust_advance.py",
                (
                    "test_current_head_and_external_witness_policy_cannot_be_self_asserted",
                    "test_stale_anchor_and_tampered_suffix_fail_closed",
                ),
            ),
        ),
        "bootstrap_fault_injection": (
            (
                "skeleton/testing/test_app_bootstrap.py",
                (
                    "test_manifest_public_contract_is_fail_closed",
                    "test_frontend_health_fallback_is_fail_closed",
                    "test_manifest_ingress_prefixes_are_validated",
                ),
            ),
            (
                "backend/tests/test_system_root_attestation.py",
                (
                    "test_component_diff_localizes_change",
                    "test_control_plane_root_changes_when_durable_evidence_changes",
                ),
            ),
        ),
        "recovery_drill": (
            (
                "skeleton/testing/test_backup_restore_integration.py",
                (
                    "test_snapshot_store_restore_drill_qualifies_real_semantics",
                    "test_corrupted_snapshot_store_backup_is_not_restorable",
                ),
            ),
            (
                "skeleton/testing/test_backup_restore_qualification.py",
                (
                    "test_authoritative_restore_and_derived_rebuild_qualify",
                    "test_receipt_requires_restore_drill_evidence",
                ),
            ),
        ),
    },
    "AC-03": {
        "resource_exhaustion": (
            (
                "skeleton/testing/test_shared_pressure.py",
                (
                    "test_two_processes_cannot_overbook_shared_concurrency",
                    "test_noisy_neighbor_cannot_consume_all_concurrency",
                    "test_queue_and_tenant_queue_caps_are_shared_across_instances",
                ),
            ),
            (
                "skeleton/testing/test_worker_pressure_quota_affinity.py",
                (
                    "test_backpressure_critical_queue_pauses",
                    "test_quota_inflight_bound",
                    "test_capacity_nonhealthy_cannot_fit",
                ),
            ),
        ),
        "load_test": (
            (
                "skeleton/testing/test_swarm_pressure_drain.py",
                (
                    "test_pressure_is_critical_without_available_workers",
                    "test_pressure_tracks_resident_capacity",
                    "test_drain_requeues_retryable_live_work",
                ),
            ),
            (
                "tests/test_control_plane_queue_backpressure.py",
                (
                    "test_shift_supervisor_stops_mutating_under_actions_pressure",
                    "test_control_plane_triggers_are_bounded",
                ),
            ),
        ),
        "soak": (
            (
                "skeleton/testing/test_process_resource_reliability_profiles.py",
                (
                    "test_process_resource_soak_keeps_runtime_resources_bounded",
                    "test_process_resource_soak_rejects_invalid_pressure",
                    "test_process_resource_soak_rejects_boolean_counts",
                ),
            ),
        ),
        "degraded_mode": (
            (
                "skeleton/testing/test_worker_pressure_quota_affinity.py",
                (
                    "test_backpressure_high_queue_throttles",
                    "test_backpressure_recovery_requires_hysteresis",
                    "test_backpressure_reset_clears_state",
                ),
            ),
            (
                "skeleton/testing/test_shared_pressure.py",
                (
                    "test_soft_shedding_protects_priority_but_drops_normal_work",
                    "test_expired_lease_is_reclaimed_after_restart",
                ),
            ),
        ),
    },
    "AC-07": {
        "mixed_version": (
            (
                "skeleton/testing/test_migration_rollback_compatibility.py",
                (
                    "test_backward_reader_must_read_exact_upgraded_snapshot",
                    "test_reader_version_must_be_rollback_source_within_window",
                    "test_reader_outside_declared_window_blocks",
                ),
            ),
        ),
        "upgrade_downgrade": (
            (
                "skeleton/testing/test_migration_rollback_compatibility.py",
                (
                    "test_complete_migration_plan_qualifies",
                    "test_rollback_must_restore_exact_pre_migration_snapshot",
                    "test_irreversible_migration_cannot_enter_rel03_plan",
                ),
            ),
        ),
        "schema_compatibility": (
            (
                "skeleton/contracts/migration_tests.py",
                (
                    "class MigrationContractError",
                    "def validate_migration_chain",
                ),
            ),
            (
                "skeleton/testing/test_migration_rollback_compatibility.py",
                (
                    "test_plan_rejects_migration_version_drift",
                    "test_receipt_requires_migration_compatibility_evidence",
                ),
            ),
        ),
        "rollback_rehearsal": (
            (
                "skeleton/testing/test_migration_rollback_compatibility.py",
                (
                    "test_rollback_must_restore_exact_pre_migration_snapshot",
                    "test_execution_evidence_failures_block",
                    "test_rejected_migration_cannot_materialize_promotion_evidence",
                ),
            ),
        ),
    },
    "AC-08": {
        "restore_drill": (
            (
                "skeleton/testing/test_backup_restore_integration.py",
                (
                    "test_snapshot_store_restore_drill_qualifies_real_semantics",
                    "test_corrupted_snapshot_store_backup_is_not_restorable",
                ),
            ),
            (
                "skeleton/testing/test_swarm_restore_validation.py",
                (
                    "test_restore_requeues_leases_and_resets_worker_liveness",
                    "test_rejects_unknown_snapshot_version",
                ),
            ),
        ),
        "tombstone_propagation": (
            (
                "skeleton/testing/test_memory_projection.py",
                (
                    "test_tombstone_deletes_projection_without_erasing_canonical_lineage",
                    "test_outbox_tombstone_removes_derived_memory",
                    "test_real_cag_and_mag_stores_delete_tombstoned_memory",
                ),
            ),
            (
                "skeleton/testing/test_data_lifecycle.py",
                (
                    "test_deletion_plan_fans_out_to_all_declared_targets",
                    "test_partial_deletion_acknowledgement_does_not_claim_completion",
                ),
            ),
        ),
        "external_reconciliation": (
            (
                "backend/core/operation_projection.py",
                (
                    "verify_projection_authority",
                    "projection is promotion evidence only after it matches durable authority",
                ),
            ),
            (
                "backend/tests/test_operation_projection.py",
                (
                    "test_full_replay_converges_to_durable_authority",
                    "test_authority_tenant_or_identity_drift_is_rejected",
                ),
            ),
        ),
        "credential_revalidation": (
            (
                "backend/tests/test_auth_security.py",
                (
                    "test_production_requires_configured_strong_jwt_secret",
                    "test_session_exchange_requires_https_when_auth_is_enforced",
                    "test_active_auth_route_retires_persisted_legacy_bootstrap_state",
                ),
            ),
            (
                "backend/core/tenant_storage_boundary.py",
                (
                    "CREDENTIAL",
                    "credentials require a dedicated secure credential store",
                ),
            ),
        ),
    },
}


class Wave4EvidenceError(RuntimeError):
    """Wave-4 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Wave4EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise Wave4EvidenceError(f"{path} must contain an object")
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


def _tracked_contract(
    root: Path,
    relative: str,
    required_tokens: tuple[str, ...],
) -> dict[str, Any]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise Wave4EvidenceError(f"proof anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise Wave4EvidenceError(f"proof anchor is not tracked: {relative}")

    text = path.read_text(encoding="utf-8")
    missing = [token for token in required_tokens if token not in text]
    if missing:
        joined = ", ".join(missing)
        raise Wave4EvidenceError(
            f"{relative} missing required proof tokens: {joined}"
        )
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(required_tokens),
    }


def build_axis_evidence(
    root: Path = ROOT,
    *,
    axis_id: str,
    expected_head: str,
) -> dict[str, Any]:
    if axis_id not in AXES:
        raise Wave4EvidenceError(f"unsupported wave-4 axis: {axis_id}")
    if not _SHA40_RE.fullmatch(expected_head):
        raise Wave4EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    closure_axes = adversarial.get("closure_axes")
    if not isinstance(closure_axes, list):
        raise Wave4EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in closure_axes
            if isinstance(row, dict) and row.get("id") == axis_id
        ),
        None,
    )
    if axis is None:
        raise Wave4EvidenceError(f"{axis_id} is missing")

    expected_modes = MODES[axis_id]
    if tuple(axis.get("required_evidence_modes") or ()) != expected_modes:
        raise Wave4EvidenceError(f"{axis_id} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == axis_id
    ]
    if len(matches) != 1:
        raise Wave4EvidenceError(
            f"expected exactly one {axis_id} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    raw_records = registry.get("records")
    if not isinstance(raw_records, list):
        raise Wave4EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in raw_records
    )
    if binding_present:
        raise Wave4EvidenceError(f"{axis_id} is already governed")

    proofs: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, str]] = []
    for mode in expected_modes:
        entries = PROOFS[axis_id][mode]
        anchors = [
            _tracked_contract(root, relative, tokens)
            for relative, tokens in entries
        ]
        required_tokens = [
            token
            for _relative, tokens in entries
            for token in tokens
        ]
        proof: dict[str, Any] = {
            "axis_id": axis_id,
            "mode": mode,
            "expected_head": expected_head,
            "anchors": anchors,
            "required_tokens": required_tokens,
        }
        proof["proof_digest"] = _digest(proof)
        proofs[mode] = proof
        evidence.append(
            {
                "source": (
                    f"p1:adversarial-wave4-evidence:{axis_id}:"
                    f"{mode}:{expected_head}"
                ),
                "digest": proof["proof_digest"],
                "category": mode,
            }
        )

    candidate: dict[str, Any] = {
        "batch_id": BATCH_ID,
        "axis_id": axis_id,
        "axis_name": axis.get("name"),
        "statement": obligation.statement,
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

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-adversarial-wave4-evidence-v1",
        "batch_id": BATCH_ID,
        "axis_id": axis_id,
        "expected_head": expected_head,
        "candidate_count": 1,
        "already_bound_count": int(binding_present),
        "candidate_binding_count": 0 if binding_present else 1,
        "required_evidence_mode_count": len(expected_modes),
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
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--axis", choices=AXES, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_axis_evidence(
            ROOT,
            axis_id=args.axis,
            expected_head=args.expected_head,
        )
    except Wave4EvidenceError as exc:
        print(f"P1 wave-4 evidence: rejected: {exc}", file=sys.stderr)
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

    print(f"P1 wave-4 evidence: OK ({args.axis})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
