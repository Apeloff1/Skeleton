"""Risk-adaptive AI execution assurance policy tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.assurance import (
    AIExecutionAssuranceInspector,
    AIExecutionAssurancePolicy,
    AssuranceLevel,
)
from skeleton.shells.ai.risk import RiskBand


def inspect(
    band,
    *,
    policy=None,
    sealed=False,
    sandbox=False,
    release=False,
    preconditions=False,
    approval=False,
    quorum=False,
):
    return AIExecutionAssuranceInspector(policy).inspect(
        band,
        sealed=sealed,
        sandbox_verified=sandbox,
        backend_id="sandbox:test" if sandbox else "shell-service-host",
        release_verified=release,
        preconditions_verified=preconditions,
        human_approved=approval,
        quorum_approved=quorum,
    )


def test_default_low_allows_standard_host_execution():
    decision = inspect(RiskBand.LOW)
    assert decision.allowed
    assert decision.required is AssuranceLevel.STANDARD


def test_default_medium_requires_seal():
    decision = inspect(RiskBand.MEDIUM)
    assert not decision.allowed
    assert any("sealed" in reason for reason in decision.reasons)
    assert inspect(RiskBand.MEDIUM, sealed=True).allowed


def test_default_high_requires_seal_and_sandbox():
    decision = inspect(RiskBand.HIGH)
    assert not decision.allowed
    assert len(decision.reasons) == 2
    assert not inspect(RiskBand.HIGH, sealed=True).allowed
    assert not inspect(RiskBand.HIGH, sandbox=True).allowed
    assert inspect(
        RiskBand.HIGH,
        sealed=True,
        sandbox=True,
    ).allowed


def test_default_critical_is_denied_even_with_controls():
    decision = inspect(
        RiskBand.CRITICAL,
        sealed=True,
        sandbox=True,
        release=True,
        preconditions=True,
        approval=True,
        quorum=True,
    )
    assert not decision.allowed
    assert decision.required is AssuranceLevel.DENIED


def test_production_medium_requires_release_and_seal():
    policy = AIExecutionAssurancePolicy.production()
    assert not inspect(
        RiskBand.MEDIUM,
        policy=policy,
        sealed=True,
    ).allowed
    assert not inspect(
        RiskBand.MEDIUM,
        policy=policy,
        release=True,
    ).allowed
    assert inspect(
        RiskBand.MEDIUM,
        policy=policy,
        sealed=True,
        release=True,
    ).allowed


def test_production_high_requires_all_controls():
    policy = AIExecutionAssurancePolicy.production()
    decision = inspect(
        RiskBand.HIGH,
        policy=policy,
        sealed=True,
        sandbox=True,
        release=True,
        preconditions=True,
        approval=True,
        quorum=True,
    )
    assert decision.allowed
    assert decision.sealed
    assert decision.sandboxed
    assert decision.release_verified
    assert decision.preconditions_verified
    assert decision.human_approved
    assert decision.quorum_approved


@pytest.mark.parametrize(
    "missing,phrase",
    [
        ("sealed", "sealed"),
        ("sandbox", "sandbox"),
        ("release", "release"),
        ("preconditions", "preconditions"),
        ("approval", "approval"),
        ("quorum", "quorum"),
    ],
)
def test_production_high_each_control_is_independently_required(
    missing,
    phrase,
):
    policy = AIExecutionAssurancePolicy.production()
    values = dict(
        sealed=True,
        sandbox=True,
        release=True,
        preconditions=True,
        approval=True,
        quorum=True,
    )
    values[missing] = False
    decision = inspect(
        RiskBand.HIGH,
        policy=policy,
        **values,
    )
    assert not decision.allowed
    assert any(phrase in reason for reason in decision.reasons)


def test_production_low_does_not_require_release():
    policy = AIExecutionAssurancePolicy.production()
    assert inspect(RiskBand.LOW, policy=policy).allowed


def test_custom_release_requirement_can_cover_low():
    policy = AIExecutionAssurancePolicy(
        require_release_bands=frozenset({RiskBand.LOW})
    )
    assert not inspect(RiskBand.LOW, policy=policy).allowed
    assert inspect(
        RiskBand.LOW,
        policy=policy,
        release=True,
    ).allowed


def test_custom_precondition_requirement_can_cover_medium():
    policy = AIExecutionAssurancePolicy(
        require_preconditions_bands=frozenset({RiskBand.MEDIUM})
    )
    assert not inspect(
        RiskBand.MEDIUM,
        policy=policy,
        sealed=True,
    ).allowed
    assert inspect(
        RiskBand.MEDIUM,
        policy=policy,
        sealed=True,
        preconditions=True,
    ).allowed


def test_custom_human_approval_requirement_can_cover_medium():
    policy = AIExecutionAssurancePolicy(
        require_human_approval_bands=frozenset({RiskBand.MEDIUM})
    )
    assert not inspect(
        RiskBand.MEDIUM,
        policy=policy,
        sealed=True,
    ).allowed
    assert inspect(
        RiskBand.MEDIUM,
        policy=policy,
        sealed=True,
        approval=True,
    ).allowed


def test_assurance_policy_accepts_string_enum_values():
    policy = AIExecutionAssurancePolicy(
        low="standard",
        medium="sealed",
        high="sandboxed",
        critical="denied",
        require_release_bands=frozenset({"medium"}),
    )
    assert policy.medium is AssuranceLevel.SEALED
    assert policy.require_release_bands == frozenset({RiskBand.MEDIUM})


def test_assurance_decision_to_dict_contains_evidence_flags():
    decision = inspect(
        RiskBand.HIGH,
        sealed=True,
        sandbox=True,
        release=True,
        preconditions=True,
        approval=True,
        quorum=True,
    )
    data = decision.to_dict()
    assert data["sealed"] is True
    assert data["sandboxed"] is True
    assert data["release_verified"] is True
    assert data["preconditions_verified"] is True
    assert data["human_approved"] is True
    assert data["quorum_approved"] is True


def test_assurance_require_raises_with_all_reasons():
    inspector = AIExecutionAssuranceInspector(
        AIExecutionAssurancePolicy.production()
    )
    with pytest.raises(RuntimeError) as caught:
        inspector.require(
            RiskBand.HIGH,
            sealed=False,
            sandbox_verified=False,
            release_verified=False,
            preconditions_verified=False,
            human_approved=False,
            quorum_approved=False,
        )
    message = str(caught.value)
    assert "sealed" in message
    assert "sandbox" in message
    assert "release" in message
    assert "preconditions" in message
    assert "approval" in message
    assert "quorum" in message


def test_assurance_require_returns_decision_when_allowed():
    inspector = AIExecutionAssuranceInspector(
        AIExecutionAssurancePolicy.production()
    )
    decision = inspector.require(
        RiskBand.HIGH,
        sealed=True,
        sandbox_verified=True,
        release_verified=True,
        preconditions_verified=True,
        human_approved=True,
        quorum_approved=True,
    )
    assert decision.allowed


def test_backend_id_is_advisory_not_sandbox_proof():
    decision = AIExecutionAssuranceInspector().inspect(
        RiskBand.HIGH,
        sealed=True,
        sandbox_verified=False,
        backend_id="sandbox:claimed",
    )
    assert not decision.allowed
    assert not decision.sandboxed


def test_sandbox_boolean_not_backend_name_controls_decision():
    decision = AIExecutionAssuranceInspector().inspect(
        RiskBand.HIGH,
        sealed=True,
        sandbox_verified=True,
        backend_id="ordinary-name",
    )
    assert decision.allowed
    assert decision.sandboxed
