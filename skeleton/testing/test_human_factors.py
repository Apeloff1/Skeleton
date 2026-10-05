from __future__ import annotations
import pytest
from skeleton.runtime.human_factors import HumanFactorsError, HumanFactorsPolicy, InteractionObservation, aggregate_assessments, assess_human_factors

def obs(**changes):
    values=dict(task_id="task-1",approvals_requested=2,approvals_overridden=0,interruptions=1,elapsed_seconds=30,confidence=.9,uncertainty=.1,degraded=False,evidence=("approval:1","trust:1"))
    values.update(changes)
    return InteractionObservation(**values)

def test_low_risk_is_deterministic_and_evidence_only():
    a=assess_human_factors(obs()); b=assess_human_factors(obs())
    assert a==b and a.risk=="low" and a.authority_scope=="evidence-only"

def test_degraded_and_override_force_high_risk():
    a=assess_human_factors(obs(approvals_overridden=1,degraded=True))
    assert a.risk=="high" and a.requires_human_review
    assert "require-fresh-explicit-approval" in a.mitigations

def test_multiple_burden_signals_accumulate_without_authority():
    a=assess_human_factors(obs(approvals_requested=6,interruptions=4,elapsed_seconds=3601,uncertainty=.8))
    assert a.risk=="high" and a.authority_scope=="evidence-only"
    assert set(a.reasons)>={"approval-burden","interruption-load","long-running-task","trust-calibration-risk"}

def test_malformed_evidence_fails_closed():
    with pytest.raises(HumanFactorsError): obs(evidence=())
    with pytest.raises(HumanFactorsError): obs(approvals_requested=0,approvals_overridden=1)
    with pytest.raises(HumanFactorsError): obs(confidence=float("nan"))

def test_policy_bounds_fail_closed():
    with pytest.raises(HumanFactorsError): HumanFactorsPolicy(max_approvals=0)
    with pytest.raises(HumanFactorsError): HumanFactorsPolicy(max_uncertainty=1.1)

def test_digest_binds_evidence_and_risk_inputs():
    assert assess_human_factors(obs(evidence=("a",))).decision_digest != assess_human_factors(obs(evidence=("b",))).decision_digest
    assert assess_human_factors(obs(interruptions=1)).decision_digest != assess_human_factors(obs(interruptions=4)).decision_digest

def test_aggregate_rejects_duplicate_identity():
    a=assess_human_factors(obs())
    with pytest.raises(HumanFactorsError): aggregate_assessments((a,a))
