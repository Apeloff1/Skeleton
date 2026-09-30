#!/usr/bin/env python3
"""Build exact-head evidence for the P1 adversarial wave-3 axes."""

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
BATCH_ID = "p1-adversarial-wave3-evidence"
OWNER_ID = "ACC-P1-EVID-04"
AXES = ("AC-05", "AC-06", "AC-17", "AC-18")

MODES: dict[str, tuple[str, ...]] = {
    "AC-05": (
        "unknown_outcome_reconciliation",
        "idempotency_replay",
        "provider_fault",
        "receipt_recovery",
    ),
    "AC-06": (
        "reconciliation_drill",
        "duplicate_delivery",
        "orphan_sweep",
        "projection_rebuild",
    ),
    "AC-17": (
        "tenant_isolation",
        "cache_key_collision",
        "dead_letter_replay",
        "artifact_acl",
    ),
    "AC-18": (
        "reindex_rebuild",
        "compaction",
        "deletion_replay",
        "derived_data_invalidation",
    ),
}

ProofEntry = tuple[str, tuple[str, ...]]
PROOFS: dict[str, dict[str, tuple[ProofEntry, ...]]] = {
    "AC-05": {
        "unknown_outcome_reconciliation": (
            (
                "skeleton/shells/reconciler.py",
                (
                    "receipt_chain_invalid",
                    "dispatches_inflight",
                    "event_order_invalid",
                ),
            ),
            (
                "skeleton/testing/test_shell_service_state_reconcile.py",
                (
                    "test_reconciler_reports_inflight_dispatch",
                    "test_reconciler_detects_receipt_tamper",
                    "test_reconciler_detects_terminal_without_start",
                ),
            ),
        ),
        "idempotency_replay": (
            (
                "skeleton/shells/ai/idempotency.py",
                (
                    "idempotency key reused with different request",
                    "idempotency key maps to different proposal",
                    "return existing",
                ),
            ),
            (
                "skeleton/testing/test_tool_receipt_store.py",
                (
                    "test_sync_durable_receipt_replays_after_restart_without_handler",
                    "test_durable_store_rejects_idempotency_key_reuse_with_different_args",
                ),
            ),
        ),
        "provider_fault": (
            (
                "skeleton/testing/test_provider_stream_reliability_profiles.py",
                (
                    "test_stream_retry_budget_is_exact_under_exhaustion",
                    "test_provider_stream_pressure_fails_closed_at_retry_budget",
                    "test_stream_never_retries_after_output_started",
                ),
            ),
        ),
        "receipt_recovery": (
            (
                "skeleton/testing/test_tool_receipt_store.py",
                (
                    "test_sync_durable_receipt_replays_after_restart_without_handler",
                    "test_durable_receipt_preserves_execution_turn_call_lineage_across_restart",
                    "test_durable_receipt_preserves_privacy_context_across_restart",
                ),
            ),
            (
                "backend/tests/test_durable_outbox.py",
                (
                    "test_journal_is_durable_and_restores",
                    "test_sequence_never_reuses_after_queue_drains_and_restart",
                    "test_failed_reconciliation_keeps_failed_entries",
                ),
            ),
        ),
    },
    "AC-06": {
        "reconciliation_drill": (
            (
                "backend/core/durable_outbox.py",
                (
                    "async def reconcile",
                    "async def confirm_one",
                    "sequence metadata checksum mismatch",
                ),
            ),
            (
                "backend/tests/test_durable_outbox.py",
                (
                    "test_async_confirmer_and_reconcile_limit",
                    "test_failed_reconciliation_keeps_failed_entries",
                ),
            ),
        ),
        "duplicate_delivery": (
            (
                "backend/core/operation_projection.py",
                (
                    "exact duplicate deliveries are idempotent",
                    "duplicate sequence predates exact receipt window",
                    "ProjectionConflictError",
                ),
            ),
            (
                "backend/tests/test_operation_projection.py",
                (
                    "test_exact_duplicate_delivery_is_idempotent",
                    "test_conflicting_duplicate_sequence_fails_closed",
                ),
            ),
        ),
        "orphan_sweep": (
            (
                "skeleton/shells/ai/durable_orphan_scan.py",
                (
                    "class DurableOrphanScanner",
                    "DurableOrphanRecordState",
                    "safe_to_delete",
                ),
            ),
            (
                "skeleton/testing/test_shell_ai_durable_orphan_scan.py",
                (
                    "test_unreachable_journal_candidate_is_delete_safe",
                    "test_sequence_index_pointing_to_orphan_requires_manual_review",
                    "test_real_cas_loser_is_detected_as_orphan",
                    "test_scanner_never_marks_committed_cas_winner_delete_safe",
                ),
            ),
        ),
        "projection_rebuild": (
            (
                "backend/core/operation_projection.py",
                (
                    "def resync_projection",
                    "stream head sequence does not match durable operation version",
                    "verify_projection_authority",
                ),
            ),
            (
                "backend/tests/test_operation_projection.py",
                (
                    "test_full_replay_converges_to_durable_authority",
                    "test_resync_binds_exact_stream_head_to_durable_version",
                    "test_reconnect_can_switch_workers_and_converge",
                ),
            ),
        ),
    },
    "AC-17": {
        "tenant_isolation": (
            (
                "backend/core/tenant_storage_boundary.py",
                (
                    "verified-tenant-mismatch",
                    "permission-not-granted",
                    "tenant_storage_namespace",
                ),
            ),
            (
                "backend/tests/test_tenant_storage_boundary.py",
                (
                    "test_verified_tenant_mismatch_fails_closed",
                    "test_storage_boundary_binds_to_durable_operation_tenant",
                ),
            ),
        ),
        "cache_key_collision": (
            (
                "backend/core/tenant_storage_boundary.py",
                (
                    "fingerprint = hashlib.sha256",
                    'return f"tenant:{fingerprint}:{normalized_purpose}"',
                ),
            ),
            (
                "backend/tests/test_tenant_storage_boundary.py",
                (
                    "test_namespace_is_stable_per_tenant_and_purpose",
                    "test_context_digest_changes_with_boundary_identity",
                ),
            ),
            (
                "skeleton/testing/test_swarm_tenant_broker.py",
                (
                    "test_tenant_broker_rejects_cross_tenant_task_collision",
                    "test_terminal_task_resubmission_preserves_cross_tenant_ownership",
                ),
            ),
        ),
        "dead_letter_replay": (
            (
                "skeleton/testing/test_swarm_dead_replay.py",
                (
                    "test_dead_task_cannot_bypass_exhausted_retry_budget",
                    "test_operator_can_explicitly_reset_retry_budget",
                ),
            ),
        ),
        "artifact_acl": (
            (
                "backend/core/tenant_storage_boundary.py",
                (
                    "class StoragePermission",
                    "ATTACHMENT_BYTES",
                    "permission-not-granted",
                ),
            ),
            (
                "backend/tests/test_tenant_storage_boundary.py",
                (
                    "test_ungranted_permission_fails_closed",
                    "test_attachment_bytes_may_use_memory_or_explicit_server_flow",
                    "test_credential_is_rejected_even_from_generic_memory_contract",
                ),
            ),
        ),
    },
    "AC-18": {
        "reindex_rebuild": (
            (
                "skeleton/testing/test_memory_projection.py",
                (
                    "test_projection_is_rebuildable_from_canonical_authority",
                    "test_real_tfidf_and_vector_stores_rebuild_from_canonical_authority",
                    "test_material_projection_rebuild_is_admitted_and_reconciled",
                ),
            ),
        ),
        "compaction": (
            (
                "skeleton/testing/test_guarded_compaction.py",
                (
                    "test_fresh_context_passes_untouched",
                    "test_rotten_context_compacts",
                    "test_buried_constraint_yields_restate_hint",
                ),
            ),
            (
                "tests/test_delta_memory_compaction.py",
                (
                    "test_window_never_exceeds_cap",
                    "test_export_load_roundtrip_preserves_window_and_tombstones",
                    "test_concurrent_writes_stay_bounded_and_consistent",
                ),
            ),
        ),
        "deletion_replay": (
            (
                "skeleton/vault/data_lifecycle.py",
                (
                    "DELETE_PENDING",
                    "cross-tenant deletion request denied",
                    "acknowledged_targets",
                ),
            ),
            (
                "skeleton/testing/test_data_lifecycle.py",
                (
                    "test_durable_registry_survives_restart_with_pending_plan",
                    "test_tenant_retention_plan_replays_only_outstanding_actions",
                    "test_duplicate_acknowledgement_fails_closed",
                ),
            ),
        ),
        "derived_data_invalidation": (
            (
                "skeleton/testing/test_memory_projection.py",
                (
                    "test_tombstone_deletes_projection_without_erasing_canonical_lineage",
                    "test_outbox_tombstone_removes_derived_memory",
                    "test_stale_pending_event_cannot_regress_rebuilt_projection",
                    "test_current_projection_event_must_match_canonical_record",
                ),
            ),
        ),
    },
}


class Wave3EvidenceError(RuntimeError):
    """Wave-3 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Wave3EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise Wave3EvidenceError(f"{path} must contain an object")
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
        raise Wave3EvidenceError(f"proof anchor missing or unsafe: {relative}")

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise Wave3EvidenceError(f"proof anchor is not tracked: {relative}")

    text = path.read_text(encoding="utf-8")
    missing = [token for token in required_tokens if token not in text]
    if missing:
        joined = ", ".join(missing)
        raise Wave3EvidenceError(
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
        raise Wave3EvidenceError(f"unsupported wave-3 axis: {axis_id}")
    if not _SHA40_RE.fullmatch(expected_head):
        raise Wave3EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    closure_axes = adversarial.get("closure_axes")
    if not isinstance(closure_axes, list):
        raise Wave3EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in closure_axes
            if isinstance(row, dict) and row.get("id") == axis_id
        ),
        None,
    )
    if axis is None:
        raise Wave3EvidenceError(f"{axis_id} is missing")

    expected_modes = MODES[axis_id]
    if tuple(axis.get("required_evidence_modes") or ()) != expected_modes:
        raise Wave3EvidenceError(f"{axis_id} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == axis_id
    ]
    if len(matches) != 1:
        raise Wave3EvidenceError(
            f"expected exactly one {axis_id} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    raw_records = registry.get("records")
    if not isinstance(raw_records, list):
        raise Wave3EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in raw_records
    )
    if binding_present:
        raise Wave3EvidenceError(f"{axis_id} is already governed")

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
                    f"p1:adversarial-wave3-evidence:{axis_id}:"
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
        "engine": "p1-adversarial-wave3-evidence-v1",
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
    except Wave3EvidenceError as exc:
        print(f"P1 wave-3 evidence: rejected: {exc}", file=sys.stderr)
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

    print(f"P1 wave-3 evidence: OK ({args.axis})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
