from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.verification import (
    ClaimKind,
    ClaimScope,
    EvidenceProducer,
    EvidenceReference,
    EvidenceRelation,
    PostconditionObservation,
    VerificationCheck,
    VerificationClaim,
    VerificationContractError,
    VerificationLevel,
    VerificationOutcome,
    VerificationRisk,
)
from skeleton.intelligence.verification_policy import (
    VerificationPolicyError,
    select_verification_policy,
)


NOW = datetime(2026, 9, 24, 3, 0, tzinfo=timezone.utc)


def _claim(
    *,
    risk: VerificationRisk = VerificationRisk.LOW,
    kind: ClaimKind = ClaimKind.FACT,
    generated_by_model: bool = False,
) -> VerificationClaim:
    return VerificationClaim(
        claim_id=str(uuid4()),
        tenant_id="tenant-a",
        text="The deployment completed successfully.",
        kind=kind,
        risk=risk,
        created_at=NOW,
        scope=ClaimScope(
            valid_from=NOW - timedelta(minutes=1),
            environment="staging",
        ),
        generated_by_model=generated_by_model,
    )


def test_claim_scope_is_first_class_and_digest_is_deterministic():
    claim = _claim(risk=VerificationRisk.MEDIUM)
    same = VerificationClaim(
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        text=claim.text,
        kind=claim.kind,
        risk=claim.risk,
        created_at=claim.created_at,
        scope=claim.scope,
        generated_by_model=claim.generated_by_model,
    )
    assert claim.digest == same.digest
    assert claim.scope.environment == "staging"

    with pytest.raises(VerificationContractError, match="valid_to"):
        ClaimScope(
            valid_from=NOW,
            valid_to=NOW - timedelta(seconds=1),
        )


def test_evidence_preserves_origin_identity_for_correlation_detection():
    claim = _claim()
    digest = "a" * 64
    first = EvidenceReference(
        evidence_id=str(uuid4()),
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        source_id="mirror-a",
        origin_id="origin-primary-document-1",
        content_digest=digest,
        locator="page:4",
        relation=EvidenceRelation.SUPPORTS,
        producer=EvidenceProducer.SOURCE,
        observed_at=NOW,
    )
    second = EvidenceReference(
        evidence_id=str(uuid4()),
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        source_id="mirror-b",
        origin_id="origin-primary-document-1",
        content_digest=digest,
        locator="page:4",
        relation=EvidenceRelation.SUPPORTS,
        producer=EvidenceProducer.SOURCE,
        observed_at=NOW,
    )
    assert first.origin_id == second.origin_id
    assert first.evidence_id != second.evidence_id


def test_postcondition_check_requires_observation_and_evidence():
    claim = _claim(
        risk=VerificationRisk.CRITICAL,
        kind=ClaimKind.ACTION_OUTCOME,
    )
    evidence_id = str(uuid4())
    observation_id = str(uuid4())
    observation = PostconditionObservation(
        observation_id=observation_id,
        postcondition_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id=claim.tenant_id,
        observed_at=NOW,
        passed=True,
        evidence_ids=(evidence_id,),
    )
    assert observation.passed is True

    check = VerificationCheck(
        check_id=str(uuid4()),
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        level=VerificationLevel.POSTCONDITION,
        outcome=VerificationOutcome.PASSED,
        verifier_id="verifier:test-suite",
        verified_at=NOW,
        evidence_ids=(evidence_id,),
        postcondition_observation_ids=(observation_id,),
        independent=True,
    )
    assert check.level is VerificationLevel.POSTCONDITION

    with pytest.raises(VerificationContractError, match="observations"):
        VerificationCheck(
            check_id=str(uuid4()),
            claim_id=claim.claim_id,
            tenant_id=claim.tenant_id,
            level=VerificationLevel.POSTCONDITION,
            outcome=VerificationOutcome.PASSED,
            verifier_id="verifier:test-suite",
            verified_at=NOW,
            evidence_ids=(evidence_id,),
            independent=True,
        )


def test_model_generated_fact_cannot_select_structural_only_verification():
    decision = select_verification_policy(
        _claim(generated_by_model=True),
    )
    assert decision.level is VerificationLevel.EVIDENCE
    assert decision.allow_model_only_evidence is False
    assert decision.min_independent_origins == 1


@pytest.mark.parametrize(
    ("risk", "expected"),
    [
        (VerificationRisk.LOW, VerificationLevel.STRUCTURAL),
        (VerificationRisk.MEDIUM, VerificationLevel.EVIDENCE),
        (VerificationRisk.HIGH, VerificationLevel.INDEPENDENT),
        (VerificationRisk.CRITICAL, VerificationLevel.POSTCONDITION),
    ],
)
def test_risk_selects_monotonic_minimum_verification_level(risk, expected):
    decision = select_verification_policy(
        _claim(risk=risk, kind=ClaimKind.HYPOTHESIS),
    )
    assert decision.level is expected


def test_irreversible_or_external_action_requires_postcondition():
    claim = _claim(
        risk=VerificationRisk.LOW,
        kind=ClaimKind.ACTION_OUTCOME,
        generated_by_model=True,
    )
    decision = select_verification_policy(
        claim,
        action_effect="irreversible",
        externally_observable_action=True,
    )
    assert decision.level is VerificationLevel.POSTCONDITION
    assert decision.require_postcondition is True
    assert decision.min_independent_origins == 2
    assert "postcondition" in decision.required_modes


def test_unknown_action_effect_fails_closed():
    with pytest.raises(VerificationPolicyError, match="unsupported"):
        select_verification_policy(
            _claim(),
            action_effect="magic",
        )
