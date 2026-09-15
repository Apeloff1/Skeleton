from __future__ import annotations

import time

from skeleton.jeeves.absorb import AbsorbSignals, Observation, Provenance
from skeleton.jeeves.absorb_claims import (
    ClaimLedger,
    ClaimStatus,
    ConsensusVerifier,
    EvidenceVote,
    SourceCalibrator,
    Stance,
)


def _observation(identifier: str, source: str, *, trust: float = 0.9) -> Observation:
    return Observation(
        observation_id=identifier,
        content="The deployment artifact matches the signed manifest",
        provenance=Provenance(
            source_id=source,
            source_type="attestation",
            observed_at=time.time(),
            trust=trust,
        ),
    )


def _signals() -> AbsorbSignals:
    return AbsorbSignals(
        novelty=0.9,
        relevance=1.0,
        information_gain=0.9,
        evidence_quality=0.9,
        urgency=0.5,
        downstream_utility=0.95,
    )


def test_same_source_cannot_manufacture_consensus() -> None:
    ledger = ClaimLedger()
    text = "one claim"
    ledger.record(text, EvidenceVote("a", "source-1", Stance.SUPPORT, time.time(), 0.9))
    assessment = ledger.record(
        text, EvidenceVote("b", "source-1", Stance.SUPPORT, time.time(), 0.9)
    )

    assert assessment.independent_sources == 1
    assert assessment.evidence_count == 1


def test_independent_refutation_marks_claim_contested() -> None:
    ledger = ClaimLedger()
    text = "one claim"
    ledger.record(text, EvidenceVote("a", "source-1", Stance.SUPPORT, time.time(), 0.9))
    assessment = ledger.record(
        text, EvidenceVote("b", "source-2", Stance.REFUTE, time.time(), 0.8)
    )

    assert assessment.status is ClaimStatus.CONTESTED
    assert assessment.contradiction > 0
    assert assessment.independent_sources == 2


def test_retraction_is_fail_closed() -> None:
    ledger = ClaimLedger()
    text = "one claim"
    ledger.record(text, EvidenceVote("a", "source-1", Stance.SUPPORT, time.time(), 0.9))

    assessment = ledger.retract(text, reason="signing key was revoked")

    assert assessment.status is ClaimStatus.RETRACTED
    assert assessment.confidence == 0
    assert assessment.contradiction == 1


def test_source_calibration_changes_effective_reliability() -> None:
    calibrator = SourceCalibrator()
    baseline = calibrator.reliability("source-1", 0.9)
    for _ in range(8):
        calibrator.adjudicate("source-1", False)

    assert calibrator.reliability("source-1", 0.9) < baseline


def test_consensus_verifier_requires_independent_sources_for_challenge() -> None:
    verifier = ConsensusVerifier(min_independent_sources=2)
    first = verifier(_observation("a", "source-1"), _signals())
    second = verifier(_observation("b", "source-2"), _signals())

    assert first.challenge_passed is False
    assert second.challenge_passed is True
    assert second.confidence >= first.confidence


def test_consensus_verifier_refuses_retracted_claim() -> None:
    ledger = ClaimLedger()
    verifier = ConsensusVerifier(ledger)
    observation = _observation("a", "source-1")
    ledger.retract(observation.content, reason="upstream attestation invalidated")

    verification = verifier(observation, _signals())

    assert verification.challenge_passed is False
    assert verification.integrity_risk == 1
    assert verification.freshness == 0
