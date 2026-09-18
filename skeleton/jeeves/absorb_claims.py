"""Cross-source consensus, source calibration, and retraction support for Jeeves absorb.

The absorb engine deliberately accepts an injectable verifier. This module
provides a stateful verifier that treats knowledge as claims with independent
support/refutation evidence instead of assuming every observation is an
isolated fact.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from .absorb import AbsorbError, AbsorbSignals, Observation, Verification, canonicalize


class Stance(str, Enum):
    SUPPORT = "support"
    REFUTE = "refute"


class ClaimStatus(str, Enum):
    ACTIVE = "active"
    CONTESTED = "contested"
    RETRACTED = "retracted"


def claim_key(text: str) -> str:
    return hashlib.sha256(canonicalize(text).encode("utf-8")).hexdigest()


def _unit(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AbsorbError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise AbsorbError(f"{name} must be finite and between 0 and 1")
    return value


@dataclass(frozen=True, slots=True)
class EvidenceVote:
    evidence_id: str
    source_id: str
    stance: Stance
    observed_at: float
    trust: float

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.source_id:
            raise AbsorbError("evidence_id and source_id must be non-empty")
        if not math.isfinite(float(self.observed_at)) or self.observed_at < 0:
            raise AbsorbError("observed_at must be a non-negative finite timestamp")
        object.__setattr__(self, "trust", _unit("trust", self.trust))


@dataclass(slots=True)
class SourcePosterior:
    """Small Beta posterior used to learn source reliability from adjudicated claims."""

    alpha: float = 2.0
    beta: float = 2.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def observe(self, correct: bool, *, weight: float = 1.0) -> None:
        if not math.isfinite(weight) or weight <= 0:
            raise AbsorbError("source calibration weight must be positive and finite")
        if correct:
            self.alpha += weight
        else:
            self.beta += weight


class SourceCalibrator:
    """Online source reliability calibration with conservative priors."""

    def __init__(self) -> None:
        self._sources: dict[str, SourcePosterior] = {}

    def reliability(self, source_id: str, declared_trust: float) -> float:
        declared = _unit("declared_trust", declared_trust)
        posterior = self._sources.get(source_id)
        if posterior is None:
            return declared
        # Do not let either self-declared trust or sparse history dominate.
        return (declared * 0.45) + (posterior.mean * 0.55)

    def adjudicate(self, source_id: str, correct: bool, *, weight: float = 1.0) -> None:
        if not source_id:
            raise AbsorbError("source_id must be non-empty")
        self._sources.setdefault(source_id, SourcePosterior()).observe(correct, weight=weight)

    def snapshot(self) -> Mapping[str, float]:
        return {
            source_id: posterior.mean
            for source_id, posterior in sorted(self._sources.items())
        }


@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    key: str
    status: ClaimStatus
    support_weight: float
    refute_weight: float
    independent_sources: int
    confidence: float
    contradiction: float
    evidence_count: int


@dataclass(slots=True)
class _ClaimRecord:
    text: str
    status: ClaimStatus = ClaimStatus.ACTIVE
    votes: dict[str, EvidenceVote] = field(default_factory=dict)
    retraction_reason: str | None = None


class ClaimLedger:
    """Evidence ledger with source de-duplication and explicit retractions.

    Each source contributes at most one effective vote per claim. New evidence
    from the same source supersedes its previous stance instead of multiplying
    influence, which makes repeated ingestion unable to manufacture consensus.
    """

    def __init__(self, *, calibrator: SourceCalibrator | None = None) -> None:
        self.calibrator = calibrator or SourceCalibrator()
        self._claims: dict[str, _ClaimRecord] = {}

    def record(self, text: str, vote: EvidenceVote) -> ClaimAssessment:
        key = claim_key(text)
        record = self._claims.setdefault(key, _ClaimRecord(text=canonicalize(text)))
        if record.status is ClaimStatus.RETRACTED:
            return self.assess(text)
        record.votes[vote.source_id] = vote
        return self.assess(text)

    def retract(self, text: str, *, reason: str) -> ClaimAssessment:
        if not reason.strip():
            raise AbsorbError("retraction reason must be non-empty")
        key = claim_key(text)
        record = self._claims.setdefault(key, _ClaimRecord(text=canonicalize(text)))
        record.status = ClaimStatus.RETRACTED
        record.retraction_reason = reason.strip()
        return self.assess(text)

    def assess(self, text: str) -> ClaimAssessment:
        key = claim_key(text)
        record = self._claims.get(key)
        if record is None:
            return ClaimAssessment(
                key=key,
                status=ClaimStatus.ACTIVE,
                support_weight=0.0,
                refute_weight=0.0,
                independent_sources=0,
                confidence=0.0,
                contradiction=0.0,
                evidence_count=0,
            )
        if record.status is ClaimStatus.RETRACTED:
            return ClaimAssessment(
                key=key,
                status=ClaimStatus.RETRACTED,
                support_weight=0.0,
                refute_weight=1.0,
                independent_sources=len(record.votes),
                confidence=0.0,
                contradiction=1.0,
                evidence_count=len(record.votes),
            )

        support = 0.0
        refute = 0.0
        for vote in record.votes.values():
            effective = self.calibrator.reliability(vote.source_id, vote.trust)
            if vote.stance is Stance.SUPPORT:
                support += effective
            else:
                refute += effective
        total = support + refute
        if total <= 0:
            confidence = 0.0
            contradiction = 0.0
        else:
            confidence = support / total
            contradiction = refute / total
        status = ClaimStatus.CONTESTED if support > 0 and refute > 0 else ClaimStatus.ACTIVE
        return ClaimAssessment(
            key=key,
            status=status,
            support_weight=support,
            refute_weight=refute,
            independent_sources=len(record.votes),
            confidence=confidence,
            contradiction=contradiction,
            evidence_count=len(record.votes),
        )


class ConsensusVerifier:
    """Absorb verifier backed by an independent-source claim ledger.

    An incoming observation is first registered as support for its canonical
    claim. Confidence combines consensus with calibrated source reliability.
    The challenge gate passes only with multiple independent sources, low
    contradiction, and a non-retracted claim.
    """

    def __init__(
        self,
        ledger: ClaimLedger | None = None,
        *,
        min_independent_sources: int = 2,
        max_challenge_contradiction: float = 0.20,
    ) -> None:
        if min_independent_sources < 1:
            raise AbsorbError("min_independent_sources must be positive")
        self.ledger = ledger or ClaimLedger()
        self.min_independent_sources = min_independent_sources
        self.max_challenge_contradiction = _unit(
            "max_challenge_contradiction", max_challenge_contradiction
        )

    def __call__(self, observation: Observation, _signals: AbsorbSignals) -> Verification:
        assessment = self.ledger.record(
            observation.content,
            EvidenceVote(
                evidence_id=f"{observation.provenance.source_id}:{observation.observation_id}",
                source_id=observation.provenance.source_id,
                stance=Stance.SUPPORT,
                observed_at=observation.provenance.observed_at,
                trust=observation.provenance.trust,
            ),
        )
        if assessment.status is ClaimStatus.RETRACTED:
            return Verification(
                confidence=0.0,
                contradiction=1.0,
                integrity_risk=1.0,
                freshness=0.0,
                challenge_passed=False,
            )

        calibrated = self.ledger.calibrator.reliability(
            observation.provenance.source_id, observation.provenance.trust
        )
        confidence = min(1.0, (assessment.confidence * 0.70) + (calibrated * 0.30))
        challenge_passed = (
            assessment.independent_sources >= self.min_independent_sources
            and assessment.contradiction <= self.max_challenge_contradiction
        )
        return Verification(
            confidence=confidence,
            contradiction=assessment.contradiction,
            integrity_risk=0.0,
            freshness=1.0,
            challenge_passed=challenge_passed,
        )
