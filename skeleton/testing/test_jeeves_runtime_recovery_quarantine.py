from __future__ import annotations

from skeleton.jeeves.agent.execution_audit import AuditEventKind
from skeleton.jeeves.agent.frontier_runtime import FrontierJeevesAgentRuntime
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.types import RiskTier


def _runtime() -> FrontierJeevesAgentRuntime:
    return FrontierJeevesAgentRuntime(
        provider_router=ProviderRouter([DeterministicProvider([])])
    )


def _append_observed_orphan(
    runtime: FrontierJeevesAgentRuntime,
    *,
    run_id: str,
    operation_id: str,
    risk: RiskTier,
) -> None:
    ledger = runtime.runtime_guard.audit_store.get_or_create(run_id)
    ledger.append(
        AuditEventKind.INTENT_BOUND,
        {
            "intent_id": f"intent-{operation_id}",
            "intent_fingerprint": "a" * 64,
            "call_id": f"call-{operation_id}",
            "tool_name": "external_write",
            "risk": risk.value,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.DECISION_MADE,
        {
            "decision_id": f"decision-{operation_id}",
            "decision_fingerprint": "b" * 64,
            "disposition": "act",
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.AUTHORIZATION_ISSUED,
        {
            "token_id": f"token-{operation_id}",
            "decision_id": f"decision-{operation_id}",
            "authorization_fingerprint": "c" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.AUTHORIZATION_CONSUMED,
        {
            "token_id": f"token-{operation_id}",
            "permit_id": f"permit-{operation_id}",
            "authorization_fingerprint": "d" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.TOOL_OBSERVED,
        {
            "call_id": f"call-{operation_id}",
            "observation_fingerprint": "e" * 64,
            "ok": True,
        },
        operation_id=operation_id,
    )


def test_observed_mutating_orphan_is_quarantined() -> None:
    runtime = _runtime()
    _append_observed_orphan(
        runtime,
        run_id="run-recovery-mutating",
        operation_id="guard-op-mutating",
        risk=RiskTier.MUTATING,
    )

    assert runtime._ambiguous_side_effects("run-recovery-mutating") == (
        "guard-op-mutating",
    )


def test_observed_external_orphan_is_quarantined() -> None:
    runtime = _runtime()
    _append_observed_orphan(
        runtime,
        run_id="run-recovery-external",
        operation_id="guard-op-external",
        risk=RiskTier.EXTERNAL,
    )

    assert runtime._ambiguous_side_effects("run-recovery-external") == (
        "guard-op-external",
    )


def test_observed_high_impact_orphan_is_quarantined() -> None:
    runtime = _runtime()
    _append_observed_orphan(
        runtime,
        run_id="run-recovery-high-impact",
        operation_id="guard-op-high-impact",
        risk=RiskTier.HIGH_IMPACT,
    )

    assert runtime._ambiguous_side_effects("run-recovery-high-impact") == (
        "guard-op-high-impact",
    )


def test_read_only_orphan_does_not_trigger_side_effect_quarantine() -> None:
    runtime = _runtime()
    _append_observed_orphan(
        runtime,
        run_id="run-recovery-read",
        operation_id="guard-op-read",
        risk=RiskTier.READ_ONLY,
    )

    assert runtime._ambiguous_side_effects("run-recovery-read") == ()


def test_finalized_mutation_is_not_quarantined() -> None:
    runtime = _runtime()
    run_id = "run-recovery-finalized"
    operation_id = "guard-op-finalized"
    _append_observed_orphan(
        runtime,
        run_id=run_id,
        operation_id=operation_id,
        risk=RiskTier.MUTATING,
    )
    ledger = runtime.runtime_guard.audit_store.get_or_create(run_id)
    ledger.append(
        AuditEventKind.EVIDENCE_INGESTED,
        {
            "evidence_ids": ["evidence-finalized"],
            "evidence_fingerprint": "f" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.TRANSITION_LEARNED,
        {
            "experience_id": "transition-finalized",
            "model_fingerprint": "1" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.EXECUTION_FINALIZED,
        {
            "outcome": "success",
            "verification_score": 1.0,
        },
        operation_id=operation_id,
    )

    assert runtime._ambiguous_side_effects(run_id) == ()


def test_unobserved_mutating_operation_does_not_claim_side_effect_ambiguity() -> None:
    runtime = _runtime()
    run_id = "run-recovery-before-tool"
    operation_id = "guard-op-before-tool"
    ledger = runtime.runtime_guard.audit_store.get_or_create(run_id)
    ledger.append(
        AuditEventKind.INTENT_BOUND,
        {
            "intent_id": "intent-before-tool",
            "intent_fingerprint": "a" * 64,
            "call_id": "call-before-tool",
            "tool_name": "external_write",
            "risk": RiskTier.MUTATING.value,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.DECISION_MADE,
        {
            "decision_id": "decision-before-tool",
            "decision_fingerprint": "b" * 64,
            "disposition": "act",
        },
        operation_id=operation_id,
    )

    assert runtime._ambiguous_side_effects(run_id) == ()