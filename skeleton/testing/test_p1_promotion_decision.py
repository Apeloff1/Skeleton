from __future__ import annotations

import pytest

from skeleton.contracts.p1_failure_journeys import P1FailureJourneyDecision
from skeleton.contracts.p1_promotion_decision import (
    P1PromotionAttestation,
    P1PromotionDecisionError,
    decide_p1_promotion,
    p1_promotion_subject_digest,
)


REPOSITORY = "Apeloff1/Skeleton"
HEAD = "a" * 40
DEFERRED = ("VOL-003", "VOL-004", "VOL-005")
PRIMARY_COUNT = 2
MASTERPLAN_COUNT = 5


def _prom02(*, promotion_ready: bool = True, **overrides: object) -> P1FailureJourneyDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "repository": REPOSITORY,
        "commit_sha": HEAD,
        "prom01_bundle_digest": "b" * 64,
        "prom01_promotion_ready": promotion_ready,
        "required_families": ("restart/crash",),
        "required_journey_classes": ("clean-machine",),
        "observation_digests": ("c" * 64,),
    }
    values.update(overrides)
    return P1FailureJourneyDecision(**values)


def _subject(prom02: P1FailureJourneyDecision) -> str:
    return p1_promotion_subject_digest(
        repository=REPOSITORY,
        commit_sha=HEAD,
        prom02_decision_digest=prom02.decision_digest,
        primary_volume_count=PRIMARY_COUNT,
        masterplan_volume_count=MASTERPLAN_COUNT,
        deferred_volume_refs=DEFERRED,
    )


def _attestation(
    prom02: P1FailureJourneyDecision,
    *,
    phase: str,
    signer_id: str,
    verifier_digest: str,
    evidence_digest: str = "e" * 64,
    signed_at_utc: str | None = None,
) -> P1PromotionAttestation:
    verification = phase == "verification"
    return P1PromotionAttestation(
        phase=phase,
        repository=REPOSITORY,
        commit_sha=HEAD,
        subject_digest=_subject(prom02),
        signer_id=signer_id,
        signer_type="ci",
        role=(
            "independent-promotion-verification"
            if verification
            else "promotion-implementation"
        ),
        signed_at_utc=signed_at_utc or (
            "2026-09-28T15:05:01Z"
            if verification
            else "2026-09-28T15:05:00Z"
        ),
        signature_method="github_identity",
        signature_ref=None,
        verifier_digest=verifier_digest,
        evidence_digest=evidence_digest,
    )


def _decide(
    prom02: P1FailureJourneyDecision | None = None,
    *,
    implementation: P1PromotionAttestation | None = None,
    verification: P1PromotionAttestation | None = None,
):
    prom02 = prom02 or _prom02()
    return decide_p1_promotion(
        prom02_bundle=prom02,
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        primary_volume_count=PRIMARY_COUNT,
        masterplan_volume_count=MASTERPLAN_COUNT,
        deferred_volume_refs=DEFERRED,
        implementation_attestation=implementation,
        verification_attestation=verification,
    )


def test_independent_exact_head_signoffs_promote_bounded_p1_frontier() -> None:
    prom02 = _prom02()
    decision = _decide(
        prom02,
        implementation=_attestation(
            prom02,
            phase="implementation",
            signer_id="github-actions:prom03-implementation",
            verifier_digest="d" * 64,
        ),
        verification=_attestation(
            prom02,
            phase="verification",
            signer_id="github-actions:prom03-independent-verifier",
            verifier_digest="f" * 64,
        ),
    )

    assert decision.promoted is True
    assert decision.reasons == ()
    assert decision.deferred_volume_count == len(DEFERRED)
    assert decision.payload()["p1_promotion_authority"] is True
    assert decision.payload()["signed_promotion"] is True
    assert decision.payload()["masterplan_maturity_authority"] is False


def test_missing_signoffs_records_explicit_rejection() -> None:
    decision = _decide()

    assert decision.promoted is False
    assert decision.reasons == (
        "missing-implementation-attestation",
        "missing-verification-attestation",
    )
    assert decision.payload()["p1_promotion_authority"] is False


def test_prom01_maturity_blocker_survives_prom02_and_blocks_promotion() -> None:
    prom02 = _prom02(promotion_ready=False)
    decision = _decide(
        prom02,
        implementation=_attestation(
            prom02,
            phase="implementation",
            signer_id="builder",
            verifier_digest="d" * 64,
        ),
        verification=_attestation(
            prom02,
            phase="verification",
            signer_id="verifier",
            verifier_digest="f" * 64,
        ),
    )

    assert decision.promoted is False
    assert "prom01-not-promotion-ready" in decision.reasons


def test_same_signer_cannot_self_verify() -> None:
    prom02 = _prom02()
    decision = _decide(
        prom02,
        implementation=_attestation(
            prom02,
            phase="implementation",
            signer_id="same-identity",
            verifier_digest="d" * 64,
        ),
        verification=_attestation(
            prom02,
            phase="verification",
            signer_id="same-identity",
            verifier_digest="f" * 64,
        ),
    )

    assert decision.promoted is False
    assert "verification-signer-not-independent" in decision.reasons


def test_same_verifier_implementation_cannot_claim_independence() -> None:
    prom02 = _prom02()
    decision = _decide(
        prom02,
        implementation=_attestation(
            prom02,
            phase="implementation",
            signer_id="builder",
            verifier_digest="d" * 64,
        ),
        verification=_attestation(
            prom02,
            phase="verification",
            signer_id="verifier",
            verifier_digest="d" * 64,
        ),
    )

    assert decision.promoted is False
    assert "verification-implementation-not-independent" in decision.reasons


def test_attestations_must_bind_identical_evidence() -> None:
    prom02 = _prom02()
    decision = _decide(
        prom02,
        implementation=_attestation(
            prom02,
            phase="implementation",
            signer_id="builder",
            verifier_digest="d" * 64,
            evidence_digest="e" * 64,
        ),
        verification=_attestation(
            prom02,
            phase="verification",
            signer_id="verifier",
            verifier_digest="f" * 64,
            evidence_digest="1" * 64,
        ),
    )

    assert decision.promoted is False
    assert "attestation-evidence-digest-mismatch" in decision.reasons


def test_verification_cannot_predate_implementation() -> None:
    prom02 = _prom02()
    decision = _decide(
        prom02,
        implementation=_attestation(
            prom02,
            phase="implementation",
            signer_id="builder",
            verifier_digest="d" * 64,
            signed_at_utc="2026-09-28T15:05:02Z",
        ),
        verification=_attestation(
            prom02,
            phase="verification",
            signer_id="verifier",
            verifier_digest="f" * 64,
            signed_at_utc="2026-09-28T15:05:01Z",
        ),
    )

    assert decision.promoted is False
    assert "verification-predates-implementation" in decision.reasons


def test_prom02_exact_head_drift_is_rejected() -> None:
    prom02 = _prom02(commit_sha="f" * 40)
    decision = _decide(prom02)

    assert decision.promoted is False
    assert "prom02-exact-head-mismatch" in decision.reasons


def test_deferred_scope_must_exactly_complete_masterplan_count() -> None:
    prom02 = _prom02()
    with pytest.raises(
        P1PromotionDecisionError,
        match="primary plus deferred volume count",
    ):
        decide_p1_promotion(
            prom02_bundle=prom02,
            expected_repository=REPOSITORY,
            expected_head=HEAD,
            primary_volume_count=PRIMARY_COUNT,
            masterplan_volume_count=MASTERPLAN_COUNT + 1,
            deferred_volume_refs=DEFERRED,
            implementation_attestation=None,
            verification_attestation=None,
        )


def test_strong_signature_method_requires_signature_reference() -> None:
    prom02 = _prom02()
    with pytest.raises(
        P1PromotionDecisionError,
        match="ci_oidc attestation requires signature_ref",
    ):
        P1PromotionAttestation(
            phase="implementation",
            repository=REPOSITORY,
            commit_sha=HEAD,
            subject_digest=_subject(prom02),
            signer_id="ci:builder",
            signer_type="ci",
            role="promotion-implementation",
            signed_at_utc="2026-09-28T15:05:00Z",
            signature_method="ci_oidc",
            signature_ref=None,
            verifier_digest="d" * 64,
            evidence_digest="e" * 64,
        )
