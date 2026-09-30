#!/usr/bin/env python3
"""Build non-authoritative exact-head evidence for P1 adversarial wave 3.

This wave covers only axes whose four required evidence modes are already
backed by tracked, executable repository controls. It never mutates the risk
registry and cannot accept risk, reduce severity, or promote maturity.
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
BATCH_ID = "p1-adversarial-wave3-nine-axes"
OWNER_ID = "ACC-P1-EVID-04"

AXIS_PROOFS: dict[str, dict[str, tuple[tuple[str, tuple[str, ...]], ...]]] = {
    "AC-02": {
        "shutdown_race": (
            (
                "skeleton/testing/test_worker_fairness_failover_shutdown.py",
                (
                    "test_shutdown_drains_queue_and_stops_workers",
                    "test_shutdown_failed_worker_can_abort",
                    "ShutdownPhase.STOPPED",
                    "ShutdownPhase.INCOMPLETE",
                ),
            ),
        ),
        "restart_replay": (
            (
                "skeleton/testing/test_state_recovery_drill.py",
                (
                    "test_operation_sqlite_restore_preserves_authority_and_outbox_order",
                    "test_engine_sqlite_bundle_restore_preserves_authoritative_ledgers",
                    "restore_operation_authority",
                    "reconcile_operation_outbox",
                ),
            ),
        ),
        "fault_injection": (
            (
                "skeleton/resilience/recovery.py",
                ("recovery_plan", "repair", "RecoveryOutcome", "attempts"),
            ),
        ),
        "state_machine_property": (
            (
                "skeleton/testing/test_worker_fairness_failover_shutdown.py",
                (
                    "ShutdownPhase.STOPPED",
                    "ShutdownPhase.INCOMPLETE",
                    "test_shutdown_no_drain_leaves_queued_but_stops",
                ),
            ),
        ),
    },
    "AC-03": {
        "resource_exhaustion": (
            (
                "skeleton/reliability/chaos.py",
                ("resource exhaustion", "FaultSpec", "cpu_burn", "ChaosMonkey"),
            ),
        ),
        "load_test": (
            (
                "skeleton/testing/process_resource_reliability_profiles.py",
                ("run_process_resource_soak_profile", "iterations", "warmup", "failed"),
            ),
        ),
        "soak": (
            (
                "skeleton/testing/test_process_resource_reliability_profiles.py",
                ("test_process_resource_soak_keeps_runtime_resources_bounded",),
            ),
        ),
        "degraded_mode": (
            (
                "skeleton/testing/test_chaos_governor.py",
                ("ChaosGovernor", "escalate_at", "recover_at", "Rung"),
            ),
        ),
    },
    "AC-04": {
        "dependency_fault": (
            (
                "backend/tests/test_ai_provider_reliability.py",
                ("_FailingAdapter", "ProviderInvocationError", "upstream-token=do-not-leak"),
            ),
        ),
        "fallback_matrix": (
            (
                "tests/test_provider_capability_matrix.py",
                (
                    "test_repository_canonical_matrix_is_complete_and_fail_closed",
                    "supported",
                    "unsupported",
                    "unknown",
                ),
            ),
            (
                "tests/test_jeeves_local_provider_policy.py",
                ("test_local_fallback_preserves_mode_policy_in_prompt",),
            ),
        ),
        "policy_regression": (
            (
                "tests/test_jeeves_local_provider_policy.py",
                ("test_local_fallback_preserves_mode_policy_in_prompt",),
            ),
            (
                "tests/test_provider_capability_matrix.py",
                ("test_guessed_status_fails_closed", "test_supported_without_evidence_fails_closed"),
            ),
        ),
        "provider_outage": (
            (
                "skeleton/testing/test_provider_stream_reliability_profiles.py",
                (
                    "test_stream_retry_budget_is_exact_under_exhaustion",
                    "test_provider_stream_pressure_fails_closed_at_retry_budget",
                    "TransientProviderError",
                ),
            ),
        ),
    },
    "AC-05": {
        "unknown_outcome_reconciliation": (
            (
                "backend/tests/test_execution_receipts.py",
                (
                    "test_receipt_round_trip_and_cas_result_round_trip",
                    "test_receipt_is_write_once_but_identical_result_is_idempotent",
                    "load_result",
                ),
            ),
        ),
        "idempotency_replay": (
            (
                "skeleton/api/idempotency.py",
                ("IdempotencyGuard", "Idempotency-Key", "def replay", "first recorded response"),
            ),
        ),
        "provider_fault": (
            (
                "backend/tests/test_ai_provider_reliability.py",
                ("_FailingAdapter", "ProviderInvocationError", "ProviderUnavailableError"),
            ),
        ),
        "receipt_recovery": (
            (
                "skeleton/testing/test_state_recovery_drill.py",
                (
                    "test_engine_sqlite_bundle_restore_preserves_authoritative_ledgers",
                    '"tool_receipts"',
                    'store["backup_digest"] == store["restore_digest"]',
                ),
            ),
        ),
    },
    "AC-06": {
        "reconciliation_drill": (
            (
                "skeleton/testing/test_state_recovery_drill.py",
                (
                    "test_operation_sqlite_restore_preserves_authority_and_outbox_order",
                    "reconcile_operation_outbox",
                ),
            ),
        ),
        "duplicate_delivery": (
            (
                "backend/tests/test_execution_receipts.py",
                ("test_receipt_is_write_once_but_identical_result_is_idempotent",),
            ),
            (
                "tests/test_duplicate_work_audit.py",
                ("test_same_head_is_explicit_duplicate_cluster", "duplicate"),
            ),
        ),
        "orphan_sweep": (
            (
                "skeleton/testing/test_shell_ai_durable_orphan_scan.py",
                (
                    "test_unreachable_journal_candidate_is_delete_safe",
                    "test_unreachable_receipt_candidate_is_delete_safe",
                    "ORPHAN_CANDIDATE",
                ),
            ),
        ),
        "projection_rebuild": (
            (
                "skeleton/testing/test_state_recovery_drill.py",
                (
                    "test_derived_rebuild_is_deterministic_from_verified_snapshot_shape",
                    "rebuild_derived_projection",
                ),
            ),
        ),
    },
    "AC-07": {
        "mixed_version": (
            (
                "skeleton/release/migration.py",
                (
                    "declared_reader_versions",
                    "reader_version",
                    "backward_read_succeeded",
                    "reader-version-outside-window",
                ),
            ),
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
                ("test_complete_migration_plan_qualifies", "rollback_succeeded", "forward_applied"),
            ),
            (
                "skeleton/testing/test_checkpoint_migrations.py",
                (
                    "test_contiguous_migrations_upgrade_to_current_version_without_mutating_input",
                    "test_newer_checkpoint_and_downgrade_fail_closed",
                    "do not support downgrade",
                ),
            ),
        ),
        "schema_compatibility": (
            (
                "skeleton/testing/test_migration_rollback_compatibility.py",
                (
                    '"schema-main"',
                    "MigrationKind.SCHEMA",
                    '"config-main"',
                    "MigrationKind.CONFIG",
                    '"state-main"',
                    "MigrationKind.STATE",
                ),
            ),
        ),
        "rollback_rehearsal": (
            (
                ".github/workflows/p1-migration-rollback-compatibility.yml",
                (
                    "Build accepted exact-head REL-03 migration evidence",
                    "rollback_succeeded=True",
                    "backward_read_succeeded=True",
                    "production_mutation_count=0",
                ),
            ),
            (
                "skeleton/testing/test_migration_rollback_compatibility.py",
                (
                    "test_rollback_must_restore_exact_pre_migration_snapshot",
                    "rollback-snapshot-mismatch",
                    "production-mutated",
                ),
            ),
        ),
    },
    "AC-09": {
        "clock_skew": (
            (
                "skeleton/testing/test_swarm_exact_lease_atomicity.py",
                (
                    "test_exact_lease_clock_failure_leaves_runtime_untouched",
                    "test_exact_lease_uses_one_clock_sample_for_commit",
                    "clock sampled twice",
                ),
            ),
        ),
        "suspend_resume": (
            (
                "skeleton/kernel/leases.py",
                ("get paused", "wake up after expiry", "stale fencing token"),
            ),
        ),
        "lease_fencing": (
            (
                "skeleton/kernel/leases.py",
                ("class FencingGate", "stale fencing token", "highest_seen"),
            ),
        ),
        "expiry_property": (
            (
                "skeleton/kernel/leases.py",
                ("is_expired", "del self._leases[resource]", "expires_at"),
            ),
        ),
    },
    "AC-18": {
        "reindex_rebuild": (
            (
                "skeleton/testing/test_state_recovery_drill.py",
                (
                    "test_derived_rebuild_is_deterministic_from_verified_snapshot_shape",
                    "rebuild_derived_projection",
                ),
            ),
        ),
        "compaction": (
            (
                "skeleton/testing/test_guarded_compaction.py",
                ("test_rotten_context_compacts", "RotGuardedCompactor", "ContextCompactor"),
            ),
            (
                "skeleton/memory/guarded_compaction.py",
                ("constraint was dropped", "constraint turns exceed the token budget"),
            ),
        ),
        "deletion_replay": (
            (
                "scripts/state_recovery_drill.py",
                ("memory-recovery-tombstoned", "memory-recovery-delete"),
            ),
            (
                "skeleton/testing/test_state_recovery_drill.py",
                ("test_derived_rebuild_includes_only_active_canonical_memory",),
            ),
        ),
        "derived_data_invalidation": (
            (
                "skeleton/testing/test_state_recovery_drill.py",
                (
                    "test_recovery_journal_forbids_derived_rebuild_before_authority_verify",
                    "expected verify_authority",
                    "rebuild_derived",
                ),
            ),
        ),
    },
    "AC-24": {
        "pairwise_fault_matrix": (
            (
                "skeleton/gate_plane/chaos_scenarios.py",
                ("class ChaosScenario", "def run_scenario", "SCENARIOS"),
            ),
        ),
        "compound_chaos": (
            (
                "skeleton/reliability/chaos.py",
                ("faults: List[FaultSpec]", "ChaosMonkey", "for fault in exp.faults"),
            ),
        ),
        "recovery_replay": (
            (
                "skeleton/testing/test_state_recovery_drill.py",
                (
                    "test_engine_sqlite_bundle_restore_preserves_authoritative_ledgers",
                    "restored_bundle_digest",
                ),
            ),
        ),
        "signed_fault_bundle": (
            (
                "skeleton/shells/ai/signed_artifact.py",
                ("class ArtifactSigner", "def sign", "def verify", "artifact signature mismatch"),
            ),
        ),
    },
}

AXIS_IDS = tuple(AXIS_PROOFS)
EXPECTED_AXIS_COUNT = 9


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
        raise Wave3EvidenceError(
            f"{relative} missing required proof tokens: {', '.join(missing)}"
        )
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(required_tokens),
    }


def build_wave3_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise Wave3EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise Wave3EvidenceError("adversarial closure axes must be a list")
    axis_rows = {
        row["id"]: row
        for row in axes
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    by_axis = {
        item.source_ref: item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL
    }
    raw_records = registry.get("records")
    if not isinstance(raw_records, list):
        raise Wave3EvidenceError("risk registry records must be a list")
    bound_ids = {
        row.get("obligation_id")
        for row in raw_records
        if isinstance(row, dict)
    }

    candidates: list[dict[str, Any]] = []
    for axis_id, mode_proofs in AXIS_PROOFS.items():
        axis = axis_rows.get(axis_id)
        obligation = by_axis.get(axis_id)
        if axis is None or obligation is None:
            raise Wave3EvidenceError(f"{axis_id} is missing from live obligations")

        expected_modes = tuple(axis.get("required_evidence_modes") or ())
        if expected_modes != tuple(mode_proofs):
            raise Wave3EvidenceError(
                f"{axis_id} required evidence modes drifted: {expected_modes!r}"
            )

        binding_present = obligation.obligation_id in bound_ids
        proofs: dict[str, dict[str, Any]] = {}
        evidence: list[dict[str, str]] = []
        for mode, entries in mode_proofs.items():
            anchors = [
                _tracked_contract(root, relative, tokens)
                for relative, tokens in entries
            ]
            required_tokens = [
                token for _relative, tokens in entries for token in tokens
            ]
            proof = {
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
                        f"p1:adversarial-wave3:{axis_id}:"
                        f"{mode}:{expected_head}"
                    ),
                    "digest": proof["proof_digest"],
                    "category": mode,
                }
            )

        candidate = {
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
        candidates.append(candidate)

    already_bound = sum(bool(row["binding_present"]) for row in candidates)
    report = {
        "schema_version": 1,
        "engine": "p1-adversarial-wave3-nine-axes-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "axis_ids": list(AXIS_IDS),
        "axis_count": len(candidates),
        "already_bound_count": already_bound,
        "candidate_binding_count": len(candidates) - already_bound,
        "non_authoritative": True,
        "creates_bindings": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
        "candidates": candidates,
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
    parser.add_argument("--print-candidates", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_wave3_evidence(ROOT, expected_head=args.expected_head)
    except Wave3EvidenceError as exc:
        print(f"P1 adversarial wave 3: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_render(report), encoding="utf-8")

    if args.print_summary:
        print(
            json.dumps(
                {
                    "axis_ids": report["axis_ids"],
                    "axis_count": report["axis_count"],
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
        print("P1_WAVE3_CANDIDATES=" + json.dumps(
            [
                {
                    "axis_id": row["axis_id"],
                    "obligation_id": row["obligation_id"],
                    "obligation_digest": row["obligation_digest"],
                    "evidence": row["evidence"],
                    "candidate_digest": row["candidate_digest"],
                }
                for row in report["candidates"]
            ],
            sort_keys=True,
            separators=(",", ":"),
        ))

    print(
        "P1 adversarial wave 3: OK "
        f"({report['axis_count']} axes; "
        f"{report['candidate_binding_count']} unbound candidates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
