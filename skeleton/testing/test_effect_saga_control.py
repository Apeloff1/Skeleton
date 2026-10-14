import pytest

from skeleton.ai.compensation_engine import CompensationEngine, CompensationPermit, CompensationSpec
from skeleton.ai.saga_control import SagaCoordinator, SagaPlan, SagaStep
from skeleton.ai.side_effect_ledger import EffectIdentity, EffectState, SideEffectLedger


def identity(key="k", effect="charge"):
    return EffectIdentity("order-1", effect, key, "payments")


def succeed(ledger, effect):
    ledger.admit(effect)
    ledger.transition(effect, EffectState.IN_FLIGHT)
    return ledger.transition(effect, EffectState.SUCCEEDED, evidence_digest="a" * 64)


def test_unknown_outcome_quarantines_retry_and_saga_progress():
    ledger = SideEffectLedger()
    effect = identity()
    ledger.admit(effect)
    ledger.transition(effect, EffectState.IN_FLIGHT)
    ledger.transition(effect, EffectState.UNKNOWN, evidence_digest="b" * 64)
    with pytest.raises(PermissionError, match="reconciliation"):
        ledger.admit(effect)
    saga = SagaCoordinator(SagaPlan("s", "payments", (SagaStep("charge", effect),)), ledger)
    with pytest.raises(PermissionError, match="reconciliation"):
        saga.advance(saga.initial())


def test_idempotency_key_collision_fails_closed():
    ledger = SideEffectLedger()
    ledger.admit(identity())
    with pytest.raises(PermissionError, match="bound"):
        ledger.admit(identity(effect="refund"))


def test_chain_is_deterministic_and_replay_detects_missing_evidence():
    effect = identity()
    first = SideEffectLedger()
    second = SideEffectLedger()
    for ledger in (first, second):
        succeed(ledger, effect)
    assert first.replay_digest == second.replay_digest
    plan = SagaPlan("s", "payments", (SagaStep("charge", effect),))
    checkpoint = SagaCoordinator(plan, first).advance(SagaCoordinator(plan, first).initial())
    SagaCoordinator(plan, first).verify_replay(checkpoint)
    with pytest.raises(PermissionError, match="missing"):
        SagaCoordinator(plan, SideEffectLedger()).verify_replay(checkpoint)


def test_compensation_permit_is_bound_to_exact_success_head():
    ledger = SideEffectLedger()
    effect = identity()
    succeed(ledger, effect)
    spec = CompensationSpec(effect, "refund-charge", "refund")
    engine = CompensationEngine(ledger)
    permit = engine.authorize(spec, authority_scope="payments")
    forged = CompensationPermit(permit.spec_digest, "0" * 64, permit.authority_scope)
    with pytest.raises(PermissionError, match="stale or forged"):
        engine.begin(spec, forged)
    engine.begin(spec, permit)
    assert ledger.head(effect.idempotency_key).state is EffectState.COMPENSATING


def test_compensation_scope_cannot_escalate_authority():
    ledger = SideEffectLedger()
    effect = identity()
    succeed(ledger, effect)
    spec = CompensationSpec(effect, "refund-charge", "refund")
    with pytest.raises(PermissionError, match="scope mismatch"):
        CompensationEngine(ledger).authorize(spec, authority_scope="admin")


def test_saga_requires_ordered_success_evidence_and_plan_identity():
    ledger = SideEffectLedger()
    a, b = identity("ka", "reserve"), identity("kb", "charge")
    succeed(ledger, b)
    plan = SagaPlan("s", "payments", (SagaStep("reserve", a), SagaStep("charge", b)))
    coordinator = SagaCoordinator(plan, ledger)
    with pytest.raises(KeyError):
        coordinator.advance(coordinator.initial())
    succeed(ledger, a)
    one = coordinator.advance(coordinator.initial())
    two = coordinator.advance(one)
    assert two.cursor == 2
    coordinator.verify_replay(two)
    other = SagaCoordinator(SagaPlan("other", "payments", plan.steps), ledger)
    with pytest.raises(PermissionError, match="another saga"):
        other.advance(one)


def test_plan_rejects_cross_scope_effects():
    with pytest.raises(PermissionError, match="scope mismatch"):
        SagaPlan("s", "payments", (SagaStep("x", EffectIdentity("o", "e", "k", "admin")),))
