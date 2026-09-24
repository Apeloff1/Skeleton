from __future__ import annotations

from skeleton.contracts.verification import ClaimKind, ProvenanceOrigin, VerificationLevel
from skeleton.intelligence.verification_policy import (
    VerificationRiskClass,
    VerificationRiskProfile,
    select_verification_requirement,
)


def test_low_risk_model_fact_still_requires_external_grounding():
    decision = select_verification_requirement(
        VerificationRiskProfile(
            risk_class=VerificationRiskClass.LOW,
            claim_kind=ClaimKind.FACT,
            claim_origin=ProvenanceOrigin.MODEL,
        )
    )
    assert decision.level is VerificationLevel.GROUNDED
    assert decision.min_independent_origins == 1
    assert "model_origin_requires_external_grounding" in decision.reasons


def test_high_risk_requires_two_independent_origins():
    decision = select_verification_requirement(
        VerificationRiskProfile(
            risk_class=VerificationRiskClass.HIGH,
            claim_kind=ClaimKind.FACT,
            claim_origin=ProvenanceOrigin.PRIMARY_SOURCE,
        )
    )
    assert decision.level is VerificationLevel.INDEPENDENT
    assert decision.min_independent_origins == 2


def test_irreversible_action_forces_high_assurance_and_postcondition():
    decision = select_verification_requirement(
        VerificationRiskProfile(
            risk_class=VerificationRiskClass.MEDIUM,
            claim_kind=ClaimKind.ACTION_OUTCOME,
            claim_origin=ProvenanceOrigin.TOOL,
            external_side_effect=True,
            irreversible=True,
        )
    )
    assert decision.level is VerificationLevel.HIGH_ASSURANCE
    assert decision.min_independent_origins == 2
    assert decision.require_postcondition is True


def test_freshness_and_scope_are_explicit_policy_requirements():
    decision = select_verification_requirement(
        VerificationRiskProfile(
            risk_class=VerificationRiskClass.LOW,
            claim_kind=ClaimKind.FACT,
            claim_origin=ProvenanceOrigin.PRIMARY_SOURCE,
            freshness_sensitive=True,
            scope_sensitive=True,
        )
    )
    assert decision.level is VerificationLevel.GROUNDED
    assert decision.min_independent_origins == 1
    assert decision.require_fresh_evidence is True
    assert decision.require_scope_match is True


def test_security_sensitive_low_risk_label_cannot_weaken_assurance():
    decision = select_verification_requirement(
        VerificationRiskProfile(
            risk_class=VerificationRiskClass.LOW,
            claim_kind=ClaimKind.INFERENCE,
            claim_origin=ProvenanceOrigin.USER,
            security_sensitive=True,
        )
    )
    assert decision.level is VerificationLevel.HIGH_ASSURANCE
    assert decision.min_independent_origins == 2
