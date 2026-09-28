from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.p1_failure_journeys import P1FailureJourneyDecision
from skeleton.contracts.p1_promotion_decision import (
    IndependentSignatureObservation,
    P1PromotionDecisionError,
    P1PromotionIntent,
    PromotionDisposition,
    finalize_p1_promotion_decision,
)


HEAD = "a" * 40
REPO = "Apeloff1/Skeleton"
DEFERRED = ("VOL-001", "VOL-002", "VOL-003")


def _prom02(
    *,
    accepted: bool = True,
    promotion_ready: bool = True,
) -> P1FailureJourneyDecision:
    return P1FailureJourneyDecision(
        accepted=accepted,
        reasons=() if accepted else ("forced-rejection",),
        repository=REPO,
        commit_sha=HEAD,
        prom01_bundle_digest="1" * 64,
        prom01_promotion_ready=promotion_ready,
        required_families=("restart/crash",),
        required_journey_classes=("clean-machine",),
        observation_digests=("2" * 64,),
    )


def _intent(
    prom02: P1FailureJourneyDecision,
    *,
    disposition: PromotionDisposition = PromotionDisposition.REJECT,
    deferred: tuple[str, ...] = DEFERRED,
) -> P1PromotionIntent:
    if disposition is PromotionDisposition.PROMOTE:
        return P1PromotionIntent(
            repository=REPO,
            commit_sha=HEAD,
            prom02_decision_digest=prom02.decision_digest,
            prom02_accepted=prom02.accepted,
            prom01_bundle_digest=prom02.prom01_bundle_digest,
            prom01_promotion_ready=prom02.prom01_promotion_ready,
            disposition=disposition,
            deferred_volume_refs=deferred,
            explicit_blockers=(),
            signer_id="release-authority:independent",
            signer_type="service",
            signer_identity_digest="3" * 64,
            public_key_fingerprint="4" * 64,
        )
    return P1PromotionIntent(
        repository=REPO,
        commit_sha=HEAD,
        prom02_decision_digest=prom02.decision_digest,
        prom02_accepted=prom02.accepted,
        prom01_bundle_digest=prom02.prom01_bundle_digest,
        prom01_promotion_ready=prom02.prom01_promotion_ready,
        disposition=disposition,
        deferred_volume_refs=deferred,
        explicit_blockers=("independent-signature-not-supplied",),
    )


def _signature(intent: P1PromotionIntent, **overrides):
    values = {
        "repository": intent.repository,
        "commit_sha": intent.commit_sha,
        "intent_digest": intent.intent_digest,
        "signer_id": intent.signer_id,
        "signer_type": intent.signer_type,
        "signer_identity_digest": intent.signer_identity_digest,
        "public_key_fingerprint": intent.public_key_fingerprint,
        "signature_digest": "5" * 64,
        "verifier_id": "openssl:ed25519-independent-verifier",
        "verifier_digest": "6" * 64,
        "signature_method": "ed25519",
        "verified": True,
        "independent": True,
    }
    values.update(overrides)
    return IndependentSignatureObservation(**values)


def test_unsigned_explicit_rejection_is_valid_terminal_decision() -> None:
    prom02 = _prom02()
    intent = _intent(prom02)

    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=prom02,
        expected_deferred_volume_refs=DEFERRED,
    )

    assert decision.accepted is True
    assert decision.disposition is PromotionDisposition.REJECT
    assert decision.promotion_granted is False
    assert decision.signed is False
    assert decision.explicit_blockers == (
        "independent-signature-not-supplied",
    )
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "p1_explicit_promotion_rejection"


def test_promote_requires_independent_signature() -> None:
    prom02 = _prom02()
    intent = _intent(
        prom02,
        disposition=PromotionDisposition.PROMOTE,
    )

    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=prom02,
        expected_deferred_volume_refs=DEFERRED,
    )

    assert decision.accepted is False
    assert "independent-signature-missing" in decision.reasons
    assert decision.promotion_granted is False


def test_verified_independent_signature_grants_terminal_candidate() -> None:
    prom02 = _prom02()
    intent = _intent(
        prom02,
        disposition=PromotionDisposition.PROMOTE,
    )
    signature = _signature(intent)

    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=prom02,
        expected_deferred_volume_refs=DEFERRED,
        signature=signature,
    )

    assert decision.accepted is True
    assert decision.signed is True
    assert decision.promotion_granted is True
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "p1_signed_promotion_decision"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"intent_digest": "0" * 64}, "signature-intent-digest-mismatch"),
        (
            {"public_key_fingerprint": "0" * 64},
            "signature-key-fingerprint-mismatch",
        ),
        (
            {"signer_identity_digest": "0" * 64},
            "signature-identity-digest-mismatch",
        ),
        (
            {"signer_type": "human"},
            "signature-signer-type-mismatch",
        ),
        ({"verified": False}, "signature-not-verified"),
        (
            {"independent": False},
            "signature-verification-not-independent",
        ),
    ),
)
def test_signature_substitution_fails_closed(
    overrides: dict,
    reason: str,
) -> None:
    prom02 = _prom02()
    intent = _intent(
        prom02,
        disposition=PromotionDisposition.PROMOTE,
    )
    signature = _signature(intent, **overrides)

    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=prom02,
        expected_deferred_volume_refs=DEFERRED,
        signature=signature,
    )

    assert decision.accepted is False
    assert reason in decision.reasons
    assert decision.promotion_granted is False


def test_agent_signer_type_is_forbidden() -> None:
    prom02 = _prom02()
    with pytest.raises(
        P1PromotionDecisionError,
        match="agent signers are forbidden",
    ):
        P1PromotionIntent(
            repository=REPO,
            commit_sha=HEAD,
            prom02_decision_digest=prom02.decision_digest,
            prom02_accepted=prom02.accepted,
            prom01_bundle_digest=prom02.prom01_bundle_digest,
            prom01_promotion_ready=prom02.prom01_promotion_ready,
            disposition=PromotionDisposition.PROMOTE,
            deferred_volume_refs=DEFERRED,
            signer_id="agent:self",
            signer_type="agent",
            signer_identity_digest="3" * 64,
            public_key_fingerprint="4" * 64,
        )


def test_signer_cannot_verify_own_signature() -> None:
    prom02 = _prom02()
    intent = _intent(
        prom02,
        disposition=PromotionDisposition.PROMOTE,
    )
    with pytest.raises(
        P1PromotionDecisionError,
        match="independent of signer",
    ):
        _signature(intent, verifier_id=intent.signer_id)


def test_deferred_scope_is_exact_and_visible() -> None:
    prom02 = _prom02()
    intent = _intent(prom02)

    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=prom02,
        expected_deferred_volume_refs=(
            "VOL-001",
            "VOL-002",
            "VOL-004",
        ),
    )

    assert decision.accepted is False
    assert "deferred-volume-scope-mismatch" in decision.reasons
    assert intent.payload()["deferred_volume_refs"] == list(DEFERRED)


def test_prom02_exact_head_and_digest_are_bound() -> None:
    prom02 = _prom02()
    intent = _intent(prom02)
    other = replace(prom02, commit_sha="b" * 40)

    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=other,
        expected_deferred_volume_refs=DEFERRED,
    )

    assert decision.accepted is False
    assert "prom02-exact-head-mismatch" in decision.reasons
    assert "prom02-decision-digest-mismatch" in decision.reasons


def test_promote_rejects_nonready_prom01_dependency() -> None:
    prom02 = _prom02(promotion_ready=False)
    intent = _intent(
        prom02,
        disposition=PromotionDisposition.PROMOTE,
    )
    signature = _signature(intent)

    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=prom02,
        expected_deferred_volume_refs=DEFERRED,
        signature=signature,
    )

    assert decision.accepted is False
    assert "prom01-not-promotion-ready" in decision.reasons
    assert decision.promotion_granted is False


def test_rejected_prom02_can_be_recorded_as_explicit_rejection() -> None:
    prom02 = _prom02(accepted=False, promotion_ready=False)
    intent = _intent(prom02)

    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=prom02,
        expected_deferred_volume_refs=DEFERRED,
    )

    assert decision.accepted is True
    assert decision.promotion_granted is False


def test_invalid_decision_cannot_materialize_evidence() -> None:
    prom02 = _prom02()
    intent = _intent(
        prom02,
        disposition=PromotionDisposition.PROMOTE,
    )
    decision = finalize_p1_promotion_decision(
        intent=intent,
        prom02=prom02,
        expected_deferred_volume_refs=DEFERRED,
    )
    assert decision.accepted is False
    with pytest.raises(
        P1PromotionDecisionError,
        match="cannot become evidence",
    ):
        decision.accepted_evidence_ref()
