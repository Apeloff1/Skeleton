"""Deterministic assurance evaluation for the converged product runtime.

Assurance is invariant-driven, not a vanity average. Hard failures block the
posture; warnings degrade it. Convergence uses evidence-backed readiness, while
durability and epistemic integrity require process-safe, attestable state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class AssuranceInvariant:
    id: str
    severity: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AssuranceReport:
    posture: str
    hard_failures: int
    warnings: int
    native_coverage_pct: float
    readiness_pct: float
    invariants: tuple[AssuranceInvariant, ...]
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def evaluate_assurance(*, lifecycle: Iterable[dict[str, Any]], operations: dict[str, Any],
                       executor_bindings: Iterable[dict[str, Any]], executor_coverage: dict[str, Any],
                       receipt_stats: dict[str, Any], readiness: dict[str, Any] | None = None) -> AssuranceReport:
    ledger = list(lifecycle); bindings = list(executor_bindings); invariants: list[AssuranceInvariant] = []
    evidence_gaps = [item for item in ledger if item.get("state") in {"evidence_gap", "receipt_unattested"}]
    anomalies = sum(len(item.get("anomalies", ())) for item in ledger)
    invariants += [
        AssuranceInvariant("lifecycle.evidence-complete", "hard", not evidence_gaps, f"{len(evidence_gaps)} lifecycle evidence gap(s)"),
        AssuranceInvariant("lifecycle.no-anomalies", "hard", anomalies == 0, f"{anomalies} lifecycle anomaly signal(s)"),
    ]

    audit_sequence = int(operations.get("audit_sequence", 0) or 0); audit_head = operations.get("audit_head")
    audit_health = operations.get("audit_health") if isinstance(operations.get("audit_health"), dict) else {}
    audit_ok = audit_sequence == 0 or isinstance(audit_head, str) and len(audit_head) == 64
    audit_runtime_ok = audit_health.get("cross_process_locking") is True and audit_health.get("verified") is True
    invariants += [
        AssuranceInvariant("audit.head-continuity", "hard", bool(audit_ok), f"sequence={audit_sequence}, head={'present' if audit_head else 'missing'}"),
        AssuranceInvariant("audit.cross-process-coherence", "hard", audit_runtime_ok,
                           f"locking={audit_health.get('lock_backend', 'missing')}, verified={audit_health.get('verified', False)}"),
    ]

    capacity = int(operations.get("outbox_capacity_remaining", 0) or 0)
    invariants += [AssuranceInvariant("queue.capacity", "hard", capacity > 0, f"{capacity} operation slots remaining"),
                   AssuranceInvariant("queue.headroom", "warning", capacity >= 32, f"{capacity} operation slots remaining; target >=32")]
    outbox_health = operations.get("outbox_health") if isinstance(operations.get("outbox_health"), dict) else {}
    process_safe = outbox_health.get("cross_process_locking") is True; leased_factory = outbox_health.get("leased_intent_factory") is True
    meta_version = int(outbox_health.get("sequence_meta_version", 0) or 0); next_sequence = int(outbox_health.get("next_sequence", 0) or 0)
    invariants += [
        AssuranceInvariant("queue.cross-process-coherence", "hard", process_safe, f"locking={outbox_health.get('lock_backend', 'missing')}"),
        AssuranceInvariant("queue.atomic-intent-staging", "hard", leased_factory, f"leased_intent_factory={leased_factory}"),
        AssuranceInvariant("queue.monotonic-sequence", "hard", meta_version >= 1 and next_sequence > 0,
                           f"metadata=v{meta_version}, next_sequence={next_sequence}"),
    ]

    unsafe = [binding for binding in bindings if binding.get("effect_class") in {"state", "external"} and not binding.get("replay_safe")]
    invariants.append(AssuranceInvariant("executors.replay-safe-effects", "hard", not unsafe,
                                         f"{len(unsafe)} state/external executor(s) lack replay safety"))
    receipt_version = int(receipt_stats.get("version", 0) or 0)
    invariants.append(AssuranceInvariant("receipts.provenance-generation", "hard", receipt_version >= 2,
                                         f"receipt schema generation v{receipt_version}"))

    curiosity = operations.get("curiosity") if isinstance(operations.get("curiosity"), dict) else {}
    verification = curiosity.get("verification") if isinstance(curiosity.get("verification"), dict) else {}
    if verification:
        registry = verification.get("evidence_registry") if isinstance(verification.get("evidence_registry"), dict) else {}
        lineage = verification.get("source_lineage") if isinstance(verification.get("source_lineage"), dict) else {}
        truth = verification.get("truth_ledger") if isinstance(verification.get("truth_ledger"), dict) else {}
        dependencies = verification.get("claim_dependencies") if isinstance(verification.get("claim_dependencies"), dict) else {}
        calibration = verification.get("calibration") if isinstance(verification.get("calibration"), dict) else {}
        knowledge = verification.get("knowledge") if isinstance(verification.get("knowledge"), dict) else {}
        policy = verification.get("verification_policy") if isinstance(verification.get("verification_policy"), dict) else {}
        truth_claims = int(truth.get("claims", 0) or 0); truth_authoritative = int(truth.get("authoritative", 0) or 0)
        truth_revoked = int(truth.get("revoked", 0) or 0); truth_expired = int(truth.get("expired", 0) or 0)
        unresolved_lineage = int(lineage.get("unresolved_lineage", 0) or 0)
        truth_counts_sane = all(x >= 0 for x in (truth_claims, truth_authoritative, truth_revoked, truth_expired)) and truth_authoritative <= truth_claims
        calibration_version = int(calibration.get("version", 0) or 0)
        invariants += [
            AssuranceInvariant("truth.gated-promotion", "hard", verification.get("truth_gated") is True,
                               f"truth_gated={verification.get('truth_gated', False)}"),
            AssuranceInvariant("truth.speculation-nonauthoritative", "hard", verification.get("speculation_authoritative") is False,
                               f"speculation_authoritative={verification.get('speculation_authoritative', True)}"),
            AssuranceInvariant("truth.model-consensus-not-evidence", "hard", verification.get("model_consensus_is_empirical_evidence") is False,
                               f"model_consensus_is_empirical_evidence={verification.get('model_consensus_is_empirical_evidence', True)}"),
            AssuranceInvariant("truth.semantic-similarity-not-identity", "hard", verification.get("semantic_similarity_is_truth_identity") is False,
                               f"semantic_similarity_is_truth_identity={verification.get('semantic_similarity_is_truth_identity', True)}"),
            AssuranceInvariant("truth.evidence-registry-coherent", "hard", registry.get("cross_process_locking") is True,
                               f"locking={registry.get('lock_backend', 'missing')}"),
            AssuranceInvariant("truth.source-lineage-coherent", "hard", lineage.get("cross_process_locking") is True,
                               f"sources={lineage.get('sources', 0)}, locking={lineage.get('lock_backend', 'missing')}"),
            AssuranceInvariant("truth.source-lineage-resolved", "warning", unresolved_lineage == 0,
                               f"{unresolved_lineage} source(s) retain unknown legacy ancestry"),
            AssuranceInvariant("truth.state-ledger-coherent", "hard", truth.get("cross_process_locking") is True and truth_counts_sane,
                               f"claims={truth_claims}, authoritative={truth_authoritative}, revoked={truth_revoked}, expired={truth_expired}"),
            AssuranceInvariant("truth.claim-dependency-coherent", "hard", dependencies.get("cross_process_locking") is True,
                               f"claims={dependencies.get('claims', 0)}, edges={dependencies.get('edges', 0)}, locking={dependencies.get('lock_backend', 'missing')}"),
            AssuranceInvariant("truth.calibration-ledger-coherent", "hard", calibration_version >= 1 and calibration.get("cross_process_locking") is True,
                               f"calibration=v{calibration_version}, locking={calibration.get('lock_backend', 'missing')}"),
            AssuranceInvariant("truth.claims-current", "warning", truth_expired == 0,
                               f"{truth_expired} verified claim(s) awaiting re-verification"),
            AssuranceInvariant("truth.four-surface-knowledge", "hard", int(knowledge.get("surface_count", 0) or 0) == 4,
                               f"surface_count={knowledge.get('surface_count', 0)}"),
            AssuranceInvariant("truth.empirical-required", "hard", policy.get("require_empirical_support") is True,
                               f"require_empirical_support={policy.get('require_empirical_support', False)}"),
            AssuranceInvariant("truth.provenance-required", "hard", policy.get("require_provenance_verified") is True,
                               f"require_provenance_verified={policy.get('require_provenance_verified', False)}"),
            AssuranceInvariant("truth.reproducibility-required", "hard", policy.get("require_reproducibility_signal") is True,
                               f"require_reproducibility_signal={policy.get('require_reproducibility_signal', False)}"),
            AssuranceInvariant("truth.independent-replication-required", "hard", policy.get("require_independent_replication_for_experiments") is True,
                               f"require_independent_replication_for_experiments={policy.get('require_independent_replication_for_experiments', False)}"),
            AssuranceInvariant("truth.falsifiability-required", "hard", policy.get("require_falsifiable_claim") is True,
                               f"require_falsifiable_claim={policy.get('require_falsifiable_claim', False)}"),
            AssuranceInvariant("truth.contradiction-blocks", "hard", policy.get("contradiction_blocks") is True,
                               f"contradiction_blocks={policy.get('contradiction_blocks', False)}"),
        ]

    coverage = float(executor_coverage.get("coverage_pct", 0.0) or 0.0)
    readiness_pct = float((readiness or {}).get("ready_pct", coverage) or 0.0)
    policy_gaps = int((readiness or {}).get("policy_gaps", 0) or 0); unsafe_actions = int((readiness or {}).get("unsafe_actions", 0) or 0)
    invariants += [
        AssuranceInvariant("convergence.policy-complete", "hard", policy_gaps == 0, f"{policy_gaps} canonical policy gap(s)"),
        AssuranceInvariant("convergence.no-unsafe-actions", "hard", unsafe_actions == 0,
                           f"{unsafe_actions} canonical action(s) violate readiness safety contracts"),
        AssuranceInvariant("convergence.native-ready-majority", "warning", readiness_pct >= 50.0,
                           f"{readiness_pct:.1f}% canonical actions are evidence-backed native-ready"),
    ]
    hard_failures = sum(not item.passed for item in invariants if item.severity == "hard")
    warnings = sum(not item.passed for item in invariants if item.severity == "warning")
    posture = "blocked" if hard_failures else ("degraded" if warnings else "healthy")
    payload = {"posture": posture, "hard_failures": hard_failures, "warnings": warnings,
               "native_coverage_pct": coverage, "readiness_pct": readiness_pct,
               "invariants": [asdict(item) for item in invariants]}
    return AssuranceReport(posture, hard_failures, warnings, coverage, readiness_pct, tuple(invariants), _digest(payload))


def verify_assurance(report: AssuranceReport) -> bool:
    payload = {"posture": report.posture, "hard_failures": report.hard_failures,
               "warnings": report.warnings, "native_coverage_pct": report.native_coverage_pct,
               "readiness_pct": report.readiness_pct, "invariants": [asdict(item) for item in report.invariants]}
    return _digest(payload) == report.attestation_sha256
