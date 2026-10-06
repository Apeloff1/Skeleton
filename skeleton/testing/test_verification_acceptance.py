from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skeleton.contracts.verification import (
    ClaimKind,
    VerificationCheck,
    VerificationClaim,
    VerificationLevel,
    VerificationOutcome,
    VerificationReceipt,
    VerificationRisk,
)
from skeleton.intelligence.verification_acceptance import (
    AcceptanceDisposition,
    VerificationAcceptanceError,
    VerificationAcceptanceGate,
    VerificationAcceptanceProfile,
    VerificationActorIdentity,
    build_independent_verification_proof,
    default_acceptance_profile,
)


NOW = datetime(2026, 10, 6, 14, 0, tzinfo=UTC)
CLAIM_ID = "11111111-1111-4111-8111-111111111111"
RECEIPT_ID = "22222222-2222-4222-8222-222222222222"
CHECK_ID = "33333333-3333-4333-8333-333333333333"
INDEPENDENT_ID = "44444444-4444-4444-8444-444444444444"
POSTCONDITION_ID = "55555555-5555-4555-8555-555555555555"
EVIDENCE_ID = "66666666-6666-4666-8666-666666666666"
CONTRADICTION_ID = "77777777-7777-4777-8777-777777777777"


def claim(
    *,
    risk: VerificationRisk = VerificationRisk.LOW,
    kind: ClaimKind = ClaimKind.FACT,
    generated_by_model: bool = True,
) -> VerificationClaim:
    return VerificationClaim(
        claim_id=CLAIM_ID,
        tenant_id="tenant-a",
        text="Deployment is healthy.",
        kind=kind,
        risk=risk,
        created_at=NOW - timedelta(minutes=5),
        generated_by_model=generated_by_model,
    )


def required_level_for(claim_value: VerificationClaim) -> VerificationLevel:
    if claim_value.kind is ClaimKind.ACTION_OUTCOME:
        return VerificationLevel.POSTCONDITION
    if claim_value.risk is VerificationRisk.CRITICAL:
        return VerificationLevel.POSTCONDITION
    if claim_value.risk is VerificationRisk.HIGH:
        return VerificationLevel.INDEPENDENT
    if claim_value.generated_by_model and claim_value.kind in {
        ClaimKind.FACT,
        ClaimKind.INTERPRETATION,
        ClaimKind.STRUCTURED_OUTPUT,
        ClaimKind.TOOL_RESULT,
        ClaimKind.ACTION_OUTCOME,
    }:
        return VerificationLevel.EVIDENCE
    if claim_value.risk is VerificationRisk.MEDIUM:
        return VerificationLevel.EVIDENCE
    return VerificationLevel.STRUCTURAL


def modes_for(level: VerificationLevel) -> tuple[str, ...]:
    if level is VerificationLevel.STRUCTURAL:
        return ("structural",)
    if level is VerificationLevel.EVIDENCE:
        return ("structural", "evidence")
    if level is VerificationLevel.INDEPENDENT:
        return ("structural", "evidence", "independent")
    return ("structural", "evidence", "independent", "postcondition")


def receipt(
    claim_value: VerificationClaim,
    *,
    level: VerificationLevel | None = None,
    verified_at: datetime = NOW - timedelta(seconds=10),
    policy_satisfied: bool = True,
    outcome: VerificationOutcome = VerificationOutcome.PASSED,
    independent: bool | None = None,
    required_modes: tuple[str, ...] | None = None,
    claim_digest: str | None = None,
    tenant_id: str | None = None,
    contradicting_evidence_ids: tuple[str, ...] = (),
    receipt_id: str = RECEIPT_ID,
) -> VerificationReceipt:
    resolved = level or required_level_for(claim_value)
    if independent is None:
        independent = resolved >= VerificationLevel.INDEPENDENT
    support = (
        (EVIDENCE_ID,)
        if policy_satisfied and resolved >= VerificationLevel.EVIDENCE
        else ()
    )
    postconditions = (
        (POSTCONDITION_ID,)
        if policy_satisfied and resolved >= VerificationLevel.POSTCONDITION
        else ()
    )
    return VerificationReceipt(
        receipt_id=receipt_id,
        claim_id=claim_value.claim_id,
        claim_digest=claim_digest or claim_value.digest,
        tenant_id=tenant_id or claim_value.tenant_id,
        outcome=outcome,
        policy_level=resolved,
        required_modes=required_modes or modes_for(resolved),
        policy_satisfied=policy_satisfied,
        verifier_id="verification-runtime:aggregate",
        verified_at=verified_at,
        check_id=CHECK_ID if policy_satisfied else None,
        supporting_evidence_ids=support,
        contradicting_evidence_ids=contradicting_evidence_ids,
        postcondition_observation_ids=postconditions,
        independent=independent,
        issues=(),
    )


def independent_check(
    claim_value: VerificationClaim,
    *,
    verified_at: datetime = NOW - timedelta(seconds=20),
    verifier_id: str = "critic-b",
    independent: bool = True,
    outcome: VerificationOutcome = VerificationOutcome.PASSED,
    check_id: str = INDEPENDENT_ID,
) -> VerificationCheck:
    return VerificationCheck(
        check_id=check_id,
        claim_id=claim_value.claim_id,
        tenant_id=claim_value.tenant_id,
        level=VerificationLevel.INDEPENDENT,
        outcome=outcome,
        verifier_id=verifier_id,
        verified_at=verified_at,
        evidence_ids=(EVIDENCE_ID,),
        independent=independent,
    )


def generator(
    *,
    actor_id: str = "generator-a",
    authority_domain: str = "generation-plane",
    process_id: str = "generation-process",
    provider_id: str = "provider-a",
) -> VerificationActorIdentity:
    return VerificationActorIdentity(
        actor_id=actor_id,
        authority_domain=authority_domain,
        process_id=process_id,
        provider_id=provider_id,
        model_id="model-a",
    )


def verifier(
    *,
    actor_id: str = "critic-b",
    authority_domain: str = "verification-plane",
    process_id: str = "verification-process",
    provider_id: str = "provider-b",
) -> VerificationActorIdentity:
    return VerificationActorIdentity(
        actor_id=actor_id,
        authority_domain=authority_domain,
        process_id=process_id,
        provider_id=provider_id,
        model_id="model-b",
    )


def proof(
    claim_value: VerificationClaim,
    receipt_value: VerificationReceipt,
    *,
    check: VerificationCheck | None = None,
    generator_identity: VerificationActorIdentity | None = None,
    verifier_identity: VerificationActorIdentity | None = None,
):
    check_value = check or independent_check(claim_value)
    verifier_value = verifier_identity or verifier(
        actor_id=check_value.verifier_id
    )
    return build_independent_verification_proof(
        claim=claim_value,
        receipt=receipt_value,
        independent_check=check_value,
        generator=generator_identity or generator(),
        verifier=verifier_value,
    )


def evaluate(
    claim_value: VerificationClaim,
    receipt_value: VerificationReceipt | None,
    *,
    proof_value=None,
    profile: VerificationAcceptanceProfile | None = None,
    action_effect: str | None = None,
    externally_observable_action: bool = False,
):
    return VerificationAcceptanceGate().evaluate(
        claim_value,
        receipt=receipt_value,
        checked_at=NOW,
        profile=profile,
        independence_proof=proof_value,
        action_effect=action_effect,
        externally_observable_action=externally_observable_action,
    )


def test_low_model_fact_with_fresh_evidence_receipt_is_accepted() -> None:
    item = claim()
    decision = evaluate(item, receipt(item))
    assert decision.accepted
    assert decision.disposition is AcceptanceDisposition.ACCEPT


def test_missing_low_risk_receipt_abstains() -> None:
    decision = evaluate(claim(), None)
    assert decision.disposition is AcceptanceDisposition.ABSTAIN
    assert "verification_receipt_missing" in decision.reasons


def test_missing_high_risk_receipt_blocks() -> None:
    decision = evaluate(claim(risk=VerificationRisk.HIGH), None)
    assert decision.disposition is AcceptanceDisposition.BLOCK


def test_receipt_claim_digest_mismatch_quarantines() -> None:
    item = claim()
    decision = evaluate(
        item,
        receipt(item, claim_digest="a" * 64),
    )
    assert decision.quarantined
    assert "verification_receipt_binding_mismatch" in decision.reasons


def test_receipt_tenant_mismatch_quarantines() -> None:
    item = claim()
    decision = evaluate(
        item,
        receipt(item, tenant_id="tenant-b"),
    )
    assert decision.quarantined


def test_future_receipt_quarantines() -> None:
    item = claim()
    decision = evaluate(
        item,
        receipt(item, verified_at=NOW + timedelta(seconds=1)),
    )
    assert decision.quarantined
    assert "verification_receipt_from_future" in decision.reasons


def test_stale_receipt_abstains_under_profile() -> None:
    item = claim()
    profile = VerificationAcceptanceProfile(
        profile_id="short",
        max_receipt_age_s=30,
        max_independent_check_age_s=30,
    )
    decision = evaluate(
        item,
        receipt(item, verified_at=NOW - timedelta(minutes=2)),
        profile=profile,
    )
    assert decision.disposition is AcceptanceDisposition.ABSTAIN
    assert "verification_receipt_stale" in decision.reasons


def test_canonical_policy_cannot_be_weakened_by_profile() -> None:
    item = claim(generated_by_model=True)
    weak = VerificationAcceptanceProfile(
        profile_id="weak",
        minimum_level=VerificationLevel.STRUCTURAL,
    )
    weak_receipt = receipt(
        item,
        level=VerificationLevel.STRUCTURAL,
        independent=False,
    )
    decision = evaluate(item, weak_receipt, profile=weak)
    assert not decision.accepted
    assert "verification_level_below_required_floor" in decision.reasons


def test_profile_can_raise_but_not_lower_canonical_floor() -> None:
    item = claim(generated_by_model=False)
    strong = VerificationAcceptanceProfile(
        profile_id="strong",
        minimum_level=VerificationLevel.EVIDENCE,
    )
    structural = receipt(
        item,
        level=VerificationLevel.STRUCTURAL,
    )
    decision = evaluate(item, structural, profile=strong)
    assert "verification_level_below_required_floor" in decision.reasons


def test_required_modes_must_cover_canonical_policy() -> None:
    item = claim()
    value = receipt(
        item,
        level=VerificationLevel.EVIDENCE,
        required_modes=("structural",),
    )
    decision = evaluate(item, value)
    assert "verification_required_modes_missing" in decision.reasons


def test_unsatisfied_receipt_abstains() -> None:
    item = claim()
    value = receipt(
        item,
        policy_satisfied=False,
        outcome=VerificationOutcome.UNKNOWN,
        independent=False,
    )
    decision = evaluate(item, value)
    assert decision.disposition is AcceptanceDisposition.ABSTAIN
    assert "verification_policy_not_satisfied" in decision.reasons
    assert "verification_outcome_not_passed" in decision.reasons


def test_passed_receipt_with_contradiction_is_quarantined() -> None:
    item = claim()
    value = receipt(
        item,
        contradicting_evidence_ids=(CONTRADICTION_ID,),
    )
    decision = evaluate(item, value)
    assert decision.quarantined
    assert "passed_receipt_contains_contradiction" in decision.reasons


def test_high_risk_receipt_requires_independent_identity_proof() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    decision = evaluate(item, value)
    assert decision.disposition is AcceptanceDisposition.BLOCK
    assert "independent_identity_proof_missing" in decision.reasons


def test_high_risk_distinct_independent_proof_is_accepted() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    identity_proof = proof(item, value)
    decision = evaluate(item, value, proof_value=identity_proof)
    assert decision.accepted


def test_independence_proof_cannot_be_replayed_to_another_receipt() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    first = receipt(item)
    identity_proof = proof(item, first)
    second = receipt(
        item,
        receipt_id="88888888-8888-4888-8888-888888888888",
    )
    decision = evaluate(item, second, proof_value=identity_proof)
    assert decision.quarantined
    assert "independent_identity_proof_binding_mismatch" in decision.reasons


def test_same_actor_cannot_claim_independence() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    check = independent_check(item, verifier_id="same-actor")
    identity_proof = proof(
        item,
        value,
        check=check,
        generator_identity=generator(actor_id="same-actor"),
        verifier_identity=verifier(actor_id="same-actor"),
    )
    decision = evaluate(item, value, proof_value=identity_proof)
    assert not decision.accepted
    assert "independent_actor_identity_collides" in decision.reasons


def test_same_authority_domain_cannot_claim_independence() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    identity_proof = proof(
        item,
        value,
        generator_identity=generator(authority_domain="shared"),
        verifier_identity=verifier(authority_domain="shared"),
    )
    decision = evaluate(item, value, proof_value=identity_proof)
    assert "independent_authority_domain_collides" in decision.reasons


def test_same_process_cannot_claim_independence() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    identity_proof = proof(
        item,
        value,
        generator_identity=generator(process_id="shared-process"),
        verifier_identity=verifier(process_id="shared-process"),
    )
    decision = evaluate(item, value, proof_value=identity_proof)
    assert "independent_process_collides" in decision.reasons


def test_high_risk_may_use_same_provider_if_authority_is_distinct() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    identity_proof = proof(
        item,
        value,
        generator_identity=generator(provider_id="provider-shared"),
        verifier_identity=verifier(provider_id="provider-shared"),
    )
    decision = evaluate(item, value, proof_value=identity_proof)
    assert decision.accepted


def test_critical_requires_distinct_provider_by_default() -> None:
    item = claim(risk=VerificationRisk.CRITICAL)
    value = receipt(item)
    identity_proof = proof(
        item,
        value,
        generator_identity=generator(provider_id="provider-shared"),
        verifier_identity=verifier(provider_id="provider-shared"),
    )
    decision = evaluate(item, value, proof_value=identity_proof)
    assert decision.disposition is AcceptanceDisposition.BLOCK
    assert "critical_independent_provider_collides" in decision.reasons


def test_critical_distinct_provider_and_postcondition_can_pass() -> None:
    item = claim(risk=VerificationRisk.CRITICAL)
    value = receipt(item)
    identity_proof = proof(item, value)
    decision = evaluate(item, value, proof_value=identity_proof)
    assert decision.accepted


def test_independent_check_postdating_receipt_is_quarantined() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item, verified_at=NOW - timedelta(seconds=20))
    check = independent_check(
        item,
        verified_at=NOW - timedelta(seconds=10),
    )
    identity_proof = proof(item, value, check=check)
    decision = evaluate(item, value, proof_value=identity_proof)
    assert decision.quarantined
    assert "independent_check_postdates_receipt" in decision.reasons


def test_stale_independent_check_blocks_high_risk() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item, verified_at=NOW - timedelta(seconds=5))
    check = independent_check(
        item,
        verified_at=NOW - timedelta(minutes=10),
    )
    profile = VerificationAcceptanceProfile(
        profile_id="fresh-independent",
        minimum_level=VerificationLevel.INDEPENDENT,
        max_receipt_age_s=3600,
        max_independent_check_age_s=60,
    )
    identity_proof = proof(item, value, check=check)
    decision = evaluate(
        item,
        value,
        proof_value=identity_proof,
        profile=profile,
    )
    assert decision.disposition is AcceptanceDisposition.BLOCK
    assert "independent_check_stale" in decision.reasons


def test_irreversible_action_escalates_low_claim_to_postcondition() -> None:
    item = claim()
    value = receipt(item, level=VerificationLevel.EVIDENCE)
    decision = evaluate(
        item,
        value,
        action_effect="irreversible",
    )
    assert not decision.accepted
    assert decision.canonical_policy_level is VerificationLevel.POSTCONDITION
    assert "verification_level_below_required_floor" in decision.reasons


def test_externally_observable_action_escalates_to_postcondition() -> None:
    item = claim()
    value = receipt(item, level=VerificationLevel.EVIDENCE)
    decision = evaluate(
        item,
        value,
        externally_observable_action=True,
    )
    assert decision.canonical_policy_level is VerificationLevel.POSTCONDITION
    assert not decision.accepted


def test_default_profiles_are_risk_scaled() -> None:
    assert default_acceptance_profile(
        claim(risk=VerificationRisk.LOW)
    ).max_receipt_age_s == 86400
    assert default_acceptance_profile(
        claim(risk=VerificationRisk.HIGH)
    ).minimum_level is VerificationLevel.INDEPENDENT
    assert default_acceptance_profile(
        claim(risk=VerificationRisk.CRITICAL)
    ).max_receipt_age_s == 900


def test_proof_builder_rejects_non_independent_check() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    check = independent_check(item, independent=False)
    with pytest.raises(
        VerificationAcceptanceError,
        match="lacks independent",
    ):
        proof(item, value, check=check)


def test_proof_builder_rejects_failed_check() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    check = independent_check(
        item,
        outcome=VerificationOutcome.FAILED,
    )
    with pytest.raises(
        VerificationAcceptanceError,
        match="must have passed",
    ):
        proof(item, value, check=check)


def test_proof_builder_rejects_verifier_identity_mismatch() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    value = receipt(item)
    check = independent_check(item, verifier_id="critic-b")
    with pytest.raises(
        VerificationAcceptanceError,
        match="does not bind",
    ):
        build_independent_verification_proof(
            claim=item,
            receipt=value,
            independent_check=check,
            generator=generator(),
            verifier=verifier(actor_id="critic-c"),
        )


def test_acceptance_decision_is_deterministic_and_non_executing() -> None:
    item = claim()
    value = receipt(item)
    first = evaluate(item, value)
    second = evaluate(item, value)
    assert first.digest == second.digest
    assert first.authority_scope == "verification-acceptance-only"
    assert first.production_authority is False
