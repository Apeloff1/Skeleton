from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_terminal_promotion import (
    IndependentPromotionAttestation,
    P1PromotionDecisionError,
    decide_p1_terminal_promotion,
    promotion_subject_digest,
)


HEAD = "a" * 40
REPOSITORY = "Apeloff1/Skeleton"
IMPLEMENTER = "chatgpt:gpt-5.6-sol"


def _prom01(*, ready: bool = False, blockers=None):
    blockers = (
        ["VOL-001:verification-unsigned"]
        if blockers is None and not ready
        else ([] if blockers is None else blockers)
    )
    return {
        "accepted": True,
        "repository": REPOSITORY,
        "commit_sha": HEAD,
        "decision_digest": "1" * 64,
        "promotion_ready": ready,
        "promotion_blockers": blockers,
    }


def _prom02(prom01=None):
    prom01 = _prom01() if prom01 is None else prom01
    return {
        "accepted": True,
        "repository": REPOSITORY,
        "commit_sha": HEAD,
        "decision_digest": "2" * 64,
        "prom01_bundle_digest": prom01["decision_digest"],
    }


def _attestation(prom01=None, prom02=None, **overrides):
    prom01 = _prom01(ready=True) if prom01 is None else prom01
    prom02 = _prom02(prom01) if prom02 is None else prom02
    values = {
        "repository": REPOSITORY,
        "commit_sha": HEAD,
        "signer_id": "human:independent-reviewer",
        "signer_type": "human",
        "role": "independent-promotion-verifier",
        "signature_method": "github_identity",
        "signature_ref": "https://github.com/Apeloff1/Skeleton/pull/9999#review",
        "subject_digest": promotion_subject_digest(
            repository=REPOSITORY,
            commit_sha=HEAD,
            prom01_bundle_digest=prom01["decision_digest"],
            prom02_bundle_digest=prom02["decision_digest"],
        ),
        "independent": True,
        "evidence_refs": (
            EvidenceRef(
                source="review://independent",
                digest="3" * 64,
                category="independent_promotion_verification",
            ),
        ),
    }
    values.update(overrides)
    return IndependentPromotionAttestation(**values)


def _decide(prom01=None, prom02=None, attestation=None):
    prom01 = _prom01() if prom01 is None else prom01
    prom02 = _prom02(prom01) if prom02 is None else prom02
    return decide_p1_terminal_promotion(
        prom01_bundle=prom01,
        prom02_bundle=prom02,
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        implementation_signer_id=IMPLEMENTER,
        attestation=attestation,
    )


def test_blockers_produce_valid_explicit_rejection() -> None:
    decision = _decide()
    assert decision.valid is True
    assert decision.outcome == "rejected"
    assert decision.promoted is False
    assert decision.signed_promotion is False
    assert decision.promotion_authority is False
    assert decision.blocker_count == 1
    assert "prom01-not-promotion-ready" in decision.reasons
    assert any(item.startswith("blocker:") for item in decision.reasons)
    evidence = decision.decision_evidence_ref()
    assert evidence.digest == decision.decision_digest


def test_promotion_ready_without_external_signature_is_rejected() -> None:
    prom01 = _prom01(ready=True)
    decision = _decide(prom01=prom01, prom02=_prom02(prom01))
    assert decision.valid is True
    assert decision.outcome == "rejected"
    assert decision.reasons == ("independent-signature-missing",)
    assert decision.promotion_authority is False


def test_independent_exact_head_signature_can_promote() -> None:
    prom01 = _prom01(ready=True)
    prom02 = _prom02(prom01)
    attestation = _attestation(prom01, prom02)
    decision = _decide(
        prom01=prom01,
        prom02=prom02,
        attestation=attestation,
    )
    assert decision.valid is True
    assert decision.outcome == "promoted"
    assert decision.reasons == ()
    assert decision.promoted is True
    assert decision.signed_promotion is True
    assert decision.promotion_authority is True
    assert decision.signer_id == "human:independent-reviewer"
    assert decision.attestation_digest == attestation.attestation_digest


def test_self_certification_is_rejected() -> None:
    prom01 = _prom01(ready=True)
    prom02 = _prom02(prom01)
    attestation = _attestation(
        prom01,
        prom02,
        signer_id=IMPLEMENTER,
    )
    decision = _decide(
        prom01=prom01,
        prom02=prom02,
        attestation=attestation,
    )
    assert decision.valid is True
    assert decision.outcome == "rejected"
    assert "self-certification-forbidden" in decision.reasons
    assert decision.promotion_authority is False


def test_stale_or_wrong_subject_attestation_is_rejected() -> None:
    prom01 = _prom01(ready=True)
    prom02 = _prom02(prom01)
    stale = _attestation(prom01, prom02, commit_sha="b" * 40)
    decision = _decide(
        prom01=prom01,
        prom02=prom02,
        attestation=stale,
    )
    assert decision.valid is False
    assert "attestation-exact-head-mismatch" in decision.reasons

    wrong_subject = _attestation(
        prom01,
        prom02,
        subject_digest="c" * 64,
    )
    decision = _decide(
        prom01=prom01,
        prom02=prom02,
        attestation=wrong_subject,
    )
    assert decision.valid is False
    assert "attestation-subject-mismatch" in decision.reasons


def test_prom02_must_link_to_exact_prom01_decision() -> None:
    prom01 = _prom01(ready=True)
    prom02 = {
        **_prom02(prom01),
        "prom01_bundle_digest": "f" * 64,
    }
    decision = _decide(prom01=prom01, prom02=prom02)
    assert decision.valid is False
    assert "prom02-prom01-link-mismatch" in decision.reasons
    with pytest.raises(
        P1PromotionDecisionError,
        match="invalid terminal decision",
    ):
        decision.decision_evidence_ref()


def test_agent_cannot_construct_promotion_attestation() -> None:
    prom01 = _prom01(ready=True)
    prom02 = _prom02(prom01)
    with pytest.raises(
        P1PromotionDecisionError,
        match="must be human, ci, or service",
    ):
        _attestation(
            prom01,
            prom02,
            signer_type="agent",
        )


def test_identity_bound_methods_require_signature_reference() -> None:
    prom01 = _prom01(ready=True)
    prom02 = _prom02(prom01)
    with pytest.raises(
        P1PromotionDecisionError,
        match="requires signature_ref",
    ):
        _attestation(
            prom01,
            prom02,
            signature_method="sigstore",
            signature_ref=None,
        )


def test_signature_while_blocked_never_overrides_blockers() -> None:
    prom01 = _prom01(ready=False)
    prom02 = _prom02(prom01)
    ready_prom01 = _prom01(ready=True)
    ready_prom02 = _prom02(ready_prom01)
    attestation = _attestation(ready_prom01, ready_prom02)
    decision = _decide(
        prom01=prom01,
        prom02=prom02,
        attestation=attestation,
    )
    assert decision.valid is True
    assert decision.outcome == "rejected"
    assert "signature-present-while-blocked" in decision.reasons
    assert decision.promotion_authority is False
