"""Host-side adjudication for adaptive frontier candidate search.

Candidate proposals are model-generated and therefore untrusted.  This module
provides the deterministic verifier callback used by CandidateScorer.  It
validates evidence references against the append-only EvidenceLedger and
computes a bounded quality score without granting the model any authority to
invent evidence, alter policy, or promote a candidate directly.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Callable

from .deliberation import CandidateProposal
from .evidence import EvidenceLedger
from .types import AgentContractError, probability, stable_fingerprint


@dataclass(frozen=True, slots=True)
class FrontierAdjudicationPolicy:
    """Bounded host policy for model-generated candidate verification."""

    maximum_evidence_refs: int = 64
    minimum_evidence_confidence: float = 0.35
    maximum_evidence_age_seconds: float | None = None
    ungrounded_score: float = 0.30
    contradiction_score: float = 0.0
    evidence_weight: float = 0.45
    integrity_weight: float = 0.20
    calibration_weight: float = 0.20
    confidence_weight: float = 0.15
    risk_penalty_per_item: float = 0.06
    assumption_penalty_per_item: float = 0.025
    depth_penalty_per_level: float = 0.01

    def __post_init__(self) -> None:
        if (
            isinstance(self.maximum_evidence_refs, bool)
            or not isinstance(self.maximum_evidence_refs, int)
            or not 1 <= self.maximum_evidence_refs <= 4096
        ):
            raise AgentContractError(
                "maximum_evidence_refs must be in [1, 4096]"
            )
        for name in (
            "minimum_evidence_confidence",
            "ungrounded_score",
            "contradiction_score",
            "evidence_weight",
            "integrity_weight",
            "calibration_weight",
            "confidence_weight",
            "risk_penalty_per_item",
            "assumption_penalty_per_item",
            "depth_penalty_per_level",
        ):
            object.__setattr__(
                self,
                name,
                probability(name, getattr(self, name)),
            )
        if self.maximum_evidence_age_seconds is not None:
            value = self.maximum_evidence_age_seconds
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise AgentContractError(
                    "maximum_evidence_age_seconds must be positive"
                )
            object.__setattr__(
                self,
                "maximum_evidence_age_seconds",
                float(value),
            )
        weight_total = (
            self.evidence_weight
            + self.integrity_weight
            + self.calibration_weight
            + self.confidence_weight
        )
        if weight_total <= 0.0:
            raise AgentContractError(
                "frontier adjudication weights must be non-zero"
            )

    @property
    def normalized_weights(self) -> tuple[float, float, float, float]:
        total = (
            self.evidence_weight
            + self.integrity_weight
            + self.calibration_weight
            + self.confidence_weight
        )
        return (
            self.evidence_weight / total,
            self.integrity_weight / total,
            self.calibration_weight / total,
            self.confidence_weight / total,
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "maximum_evidence_refs": self.maximum_evidence_refs,
                "minimum_evidence_confidence": (
                    self.minimum_evidence_confidence
                ),
                "maximum_evidence_age_seconds": (
                    self.maximum_evidence_age_seconds
                ),
                "ungrounded_score": self.ungrounded_score,
                "contradiction_score": self.contradiction_score,
                "weights": self.normalized_weights,
                "risk_penalty_per_item": self.risk_penalty_per_item,
                "assumption_penalty_per_item": (
                    self.assumption_penalty_per_item
                ),
                "depth_penalty_per_level": self.depth_penalty_per_level,
            }
        )


@dataclass(frozen=True, slots=True)
class FrontierAdjudicationReport:
    candidate_id: str
    score: float
    evidence_quality: float
    evidence_integrity: float
    confidence_alignment: float
    matched_evidence: int
    missing_evidence: int
    stale_evidence: int
    contradictions: int
    rejected: bool
    reasons: tuple[str, ...]
    policy_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "score", probability("score", self.score))
        for name in (
            "evidence_quality",
            "evidence_integrity",
            "confidence_alignment",
        ):
            object.__setattr__(
                self,
                name,
                probability(name, getattr(self, name)),
            )
        for name in (
            "matched_evidence",
            "missing_evidence",
            "stale_evidence",
            "contradictions",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise AgentContractError(
                    f"{name} must be a non-negative integer"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "score": self.score,
            "evidence_quality": self.evidence_quality,
            "evidence_integrity": self.evidence_integrity,
            "confidence_alignment": self.confidence_alignment,
            "matched_evidence": self.matched_evidence,
            "missing_evidence": self.missing_evidence,
            "stale_evidence": self.stale_evidence,
            "contradictions": self.contradictions,
            "rejected": self.rejected,
            "reasons": list(self.reasons),
            "policy_fingerprint": self.policy_fingerprint,
            "fingerprint": self.fingerprint,
        }


class HostCandidateAdjudicator:
    """Verify candidate grounding using only host-trusted ledger state.

    The public score method matches deliberation.ProposalVerifier and therefore
    returns a probability in [0, 1].  inspect exposes the reasons for audit and
    tests without changing CandidateScorer's existing callback contract.
    """

    def __init__(
        self,
        ledger: EvidenceLedger,
        *,
        policy: FrontierAdjudicationPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(ledger, EvidenceLedger):
            raise TypeError("ledger must be EvidenceLedger")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.ledger = ledger
        self.policy = policy or FrontierAdjudicationPolicy()
        self._clock = clock

    def score(self, candidate: CandidateProposal) -> float:
        return self.inspect(candidate).score

    def inspect(
        self,
        candidate: CandidateProposal,
    ) -> FrontierAdjudicationReport:
        if not isinstance(candidate, CandidateProposal):
            raise TypeError("candidate must be CandidateProposal")

        refs = candidate.evidence
        reasons: list[str] = []
        if len(refs) > self.policy.maximum_evidence_refs:
            reasons.append("candidate evidence reference bound exceeded")
            return self._report(
                candidate,
                score=0.0,
                evidence_quality=0.0,
                evidence_integrity=0.0,
                confidence_alignment=0.0,
                matched=0,
                missing=len(refs),
                stale=0,
                contradictions=0,
                rejected=True,
                reasons=reasons,
            )

        if not refs:
            reasons.append("candidate has no ledger evidence")
            penalty = self._candidate_penalty(candidate)
            return self._report(
                candidate,
                score=max(
                    0.0,
                    self.policy.ungrounded_score - penalty,
                ),
                evidence_quality=0.0,
                evidence_integrity=0.0,
                confidence_alignment=max(
                    0.0,
                    1.0 - candidate.confidence,
                ),
                matched=0,
                missing=0,
                stale=0,
                contradictions=0,
                rejected=False,
                reasons=reasons,
            )

        now = float(self._clock())
        if not math.isfinite(now) or now < 0.0:
            raise AgentContractError(
                "frontier adjudication clock returned invalid time"
            )

        matched = 0
        missing = 0
        stale = 0
        authoritative_confidences: list[float] = []
        referenced_ids: list[str] = []
        invalid_identity = False

        for ref in refs:
            artifact = self.ledger.get(ref.evidence_id)
            if artifact is None:
                missing += 1
                invalid_identity = True
                reasons.append(
                    f"missing ledger evidence {ref.evidence_id}"
                )
                continue

            referenced_ids.append(artifact.evidence_id)
            identity_problems = []
            if artifact.fingerprint != ref.fingerprint:
                identity_problems.append("fingerprint")
            if artifact.kind is not ref.kind:
                identity_problems.append("kind")
            if artifact.source != ref.source:
                identity_problems.append("source")
            if identity_problems:
                invalid_identity = True
                reasons.append(
                    "evidence identity mismatch "
                    f"{ref.evidence_id}: "
                    + ",".join(identity_problems)
                )
                continue

            if (
                min(artifact.confidence, ref.confidence)
                < self.policy.minimum_evidence_confidence
            ):
                invalid_identity = True
                reasons.append(
                    f"evidence confidence below threshold "
                    f"{ref.evidence_id}"
                )
                continue

            age_limit = self.policy.maximum_evidence_age_seconds
            if age_limit is not None:
                age = now - artifact.observed_at
                if age < 0.0 or age > age_limit:
                    stale += 1
                    invalid_identity = True
                    reasons.append(
                        f"stale ledger evidence {ref.evidence_id}"
                    )
                    continue

            matched += 1
            authoritative_confidences.append(
                min(artifact.confidence, ref.confidence)
            )

        contradictions = self.ledger.contradictions_for(
            referenced_ids
        )
        if contradictions:
            reasons.append(
                "candidate references contradictory ledger evidence"
            )

        if invalid_identity:
            return self._report(
                candidate,
                score=0.0,
                evidence_quality=(
                    sum(authoritative_confidences)
                    / len(authoritative_confidences)
                    if authoritative_confidences
                    else 0.0
                ),
                evidence_integrity=matched / len(refs),
                confidence_alignment=0.0,
                matched=matched,
                missing=missing,
                stale=stale,
                contradictions=len(contradictions),
                rejected=True,
                reasons=reasons,
            )

        if contradictions:
            return self._report(
                candidate,
                score=self.policy.contradiction_score,
                evidence_quality=(
                    sum(authoritative_confidences)
                    / len(authoritative_confidences)
                ),
                evidence_integrity=matched / len(refs),
                confidence_alignment=0.0,
                matched=matched,
                missing=missing,
                stale=stale,
                contradictions=len(contradictions),
                rejected=True,
                reasons=reasons,
            )

        evidence_quality = (
            sum(authoritative_confidences)
            / len(authoritative_confidences)
        )
        integrity = matched / len(refs)
        confidence_alignment = max(
            0.0,
            1.0 - abs(
                candidate.confidence - evidence_quality
            ),
        )
        ew, iw, aw, cw = self.policy.normalized_weights
        base = (
            evidence_quality * ew
            + integrity * iw
            + confidence_alignment * aw
            + candidate.confidence * cw
        )
        penalty = self._candidate_penalty(candidate)
        score = max(0.0, min(1.0, base - penalty))
        if candidate.risks:
            reasons.append(
                f"candidate risk penalty={min(1.0, len(candidate.risks) * self.policy.risk_penalty_per_item):.3f}"
            )
        if candidate.assumptions:
            reasons.append(
                "candidate assumption penalty="
                f"{min(1.0, len(candidate.assumptions) * self.policy.assumption_penalty_per_item):.3f}"
            )
        reasons.append(
            f"ledger evidence quality={evidence_quality:.3f}"
        )
        reasons.append(
            f"evidence identity integrity={integrity:.3f}"
        )
        reasons.append(
            f"confidence alignment={confidence_alignment:.3f}"
        )
        return self._report(
            candidate,
            score=score,
            evidence_quality=evidence_quality,
            evidence_integrity=integrity,
            confidence_alignment=confidence_alignment,
            matched=matched,
            missing=missing,
            stale=stale,
            contradictions=0,
            rejected=False,
            reasons=reasons,
        )

    def _candidate_penalty(
        self,
        candidate: CandidateProposal,
    ) -> float:
        return min(
            1.0,
            len(candidate.risks)
            * self.policy.risk_penalty_per_item
            + len(candidate.assumptions)
            * self.policy.assumption_penalty_per_item
            + candidate.depth
            * self.policy.depth_penalty_per_level,
        )

    def _report(
        self,
        candidate: CandidateProposal,
        *,
        score: float,
        evidence_quality: float,
        evidence_integrity: float,
        confidence_alignment: float,
        matched: int,
        missing: int,
        stale: int,
        contradictions: int,
        rejected: bool,
        reasons: list[str],
    ) -> FrontierAdjudicationReport:
        payload = {
            "candidate": candidate.fingerprint,
            "score": score,
            "evidence_quality": evidence_quality,
            "evidence_integrity": evidence_integrity,
            "confidence_alignment": confidence_alignment,
            "matched": matched,
            "missing": missing,
            "stale": stale,
            "contradictions": contradictions,
            "rejected": rejected,
            "reasons": tuple(reasons),
            "ledger": self.ledger.fingerprint,
            "policy": self.policy.fingerprint,
        }
        return FrontierAdjudicationReport(
            candidate_id=candidate.candidate_id,
            score=max(0.0, min(1.0, score)),
            evidence_quality=max(
                0.0,
                min(1.0, evidence_quality),
            ),
            evidence_integrity=max(
                0.0,
                min(1.0, evidence_integrity),
            ),
            confidence_alignment=max(
                0.0,
                min(1.0, confidence_alignment),
            ),
            matched_evidence=matched,
            missing_evidence=missing,
            stale_evidence=stale,
            contradictions=contradictions,
            rejected=rejected,
            reasons=tuple(reasons),
            policy_fingerprint=self.policy.fingerprint,
            fingerprint=stable_fingerprint(payload),
        )
