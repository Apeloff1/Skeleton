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


@dataclass(frozen=True, slots=True)
class HostCandidateAdjudicationReport:
    """Host-derived evidence custody and contradiction assessment.

    This richer report is intentionally separate from FrontierAdjudicationReport.
    inspect preserves the historical scoring contract while adjudicate exposes
    custody, fingerprint, source-diversity, and contradiction metrics.
    """

    candidate_id: str
    score: float
    custody_fraction: float
    fingerprint_fraction: float
    identity_fraction: float
    source_diversity: float
    confidence_quality: float
    contradiction_count: int
    contradiction_rate: float
    known_evidence_count: int
    unknown_evidence_count: int
    fingerprint_mismatch_count: int
    identity_mismatch_count: int
    stale_evidence_count: int
    rejected: bool
    reasons: tuple[str, ...]
    policy_fingerprint: str
    ledger_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        for name in (
            "score",
            "custody_fraction",
            "fingerprint_fraction",
            "identity_fraction",
            "source_diversity",
            "confidence_quality",
            "contradiction_rate",
        ):
            object.__setattr__(
                self,
                name,
                probability(name, getattr(self, name)),
            )
        for name in (
            "contradiction_count",
            "known_evidence_count",
            "unknown_evidence_count",
            "fingerprint_mismatch_count",
            "identity_mismatch_count",
            "stale_evidence_count",
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
        if not self.candidate_id:
            raise AgentContractError("candidate_id is required")
        for name in (
            "policy_fingerprint",
            "ledger_fingerprint",
            "fingerprint",
        ):
            value = getattr(self, name)
            if len(value) != 64:
                raise AgentContractError(
                    f"{name} must be SHA-256 hex"
                )

    @property
    def total_evidence_count(self) -> int:
        return self.known_evidence_count + self.unknown_evidence_count

    @property
    def ok(self) -> bool:
        return not self.rejected

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "score": self.score,
            "custody_fraction": self.custody_fraction,
            "fingerprint_fraction": self.fingerprint_fraction,
            "identity_fraction": self.identity_fraction,
            "source_diversity": self.source_diversity,
            "confidence_quality": self.confidence_quality,
            "contradiction_count": self.contradiction_count,
            "contradiction_rate": self.contradiction_rate,
            "known_evidence_count": self.known_evidence_count,
            "unknown_evidence_count": self.unknown_evidence_count,
            "fingerprint_mismatch_count": self.fingerprint_mismatch_count,
            "identity_mismatch_count": self.identity_mismatch_count,
            "stale_evidence_count": self.stale_evidence_count,
            "total_evidence_count": self.total_evidence_count,
            "rejected": self.rejected,
            "ok": self.ok,
            "reasons": list(self.reasons),
            "policy_fingerprint": self.policy_fingerprint,
            "ledger_fingerprint": self.ledger_fingerprint,
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

    def adjudicate(
        self,
        candidate: CandidateProposal,
    ) -> HostCandidateAdjudicationReport:
        """Return host-trusted custody and contradiction metrics."""
        if not isinstance(candidate, CandidateProposal):
            raise TypeError("candidate must be CandidateProposal")

        refs = candidate.evidence
        if len(refs) > self.policy.maximum_evidence_refs:
            return self._host_report(
                candidate,
                score=0.0,
                custody_fraction=0.0,
                fingerprint_fraction=0.0,
                identity_fraction=0.0,
                source_diversity=0.0,
                confidence_quality=0.0,
                contradiction_count=0,
                contradiction_rate=0.0,
                known_evidence_count=0,
                unknown_evidence_count=len(refs),
                fingerprint_mismatch_count=0,
                identity_mismatch_count=0,
                stale_evidence_count=0,
                rejected=True,
                reasons=(
                    "evidence_reference_bound_exceeded="
                    f"{len(refs)}>{self.policy.maximum_evidence_refs}",
                ),
            )

        now = float(self._clock())
        if not math.isfinite(now) or now < 0.0:
            raise AgentContractError(
                "frontier adjudication clock returned invalid time"
            )

        known_ids: list[str] = []
        known_count = 0
        unknown_count = 0
        fingerprint_matches = 0
        fingerprint_mismatches = 0
        identity_matches = 0
        identity_mismatches = 0
        stale_count = 0
        low_confidence_count = 0
        sources: set[str] = set()
        confidences: list[float] = []

        for ref in refs:
            artifact = self.ledger.get(ref.evidence_id)
            if artifact is None:
                unknown_count += 1
                continue

            known_count += 1
            known_ids.append(artifact.evidence_id)
            sources.add(artifact.source)
            confidence = min(artifact.confidence, ref.confidence)
            confidences.append(confidence)

            if artifact.fingerprint == ref.fingerprint:
                fingerprint_matches += 1
            else:
                fingerprint_mismatches += 1

            if artifact.kind is ref.kind and artifact.source == ref.source:
                identity_matches += 1
            else:
                identity_mismatches += 1

            if confidence < self.policy.minimum_evidence_confidence:
                low_confidence_count += 1

            age_limit = self.policy.maximum_evidence_age_seconds
            if age_limit is not None:
                age = now - artifact.observed_at
                if age < 0.0 or age > age_limit:
                    stale_count += 1

        total = len(refs)
        custody_fraction = known_count / total if total else 0.0
        fingerprint_fraction = (
            fingerprint_matches / known_count if known_count else 0.0
        )
        identity_fraction = (
            identity_matches / known_count if known_count else 0.0
        )
        source_diversity = (
            len(sources) / known_count if known_count else 0.0
        )
        confidence_quality = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        contradictions = self.ledger.contradictions_for(known_ids)
        pair_count = known_count * (known_count - 1) // 2
        contradiction_rate = (
            min(1.0, len(contradictions) / pair_count)
            if pair_count
            else 0.0
        )
        stale_fraction = stale_count / known_count if known_count else 0.0
        low_confidence_fraction = (
            low_confidence_count / known_count if known_count else 0.0
        )

        base = (
            0.24 * candidate.confidence
            + 0.28 * confidence_quality
            + 0.18 * custody_fraction
            + 0.12 * fingerprint_fraction
            + 0.08 * identity_fraction
            + 0.10 * source_diversity
        )
        integrity_penalty = (
            0.50 * (1.0 - custody_fraction)
            + 0.35 * (1.0 - fingerprint_fraction)
            + 0.25 * (1.0 - identity_fraction)
            + 0.50 * contradiction_rate
            + 0.20 * stale_fraction
            + 0.15 * low_confidence_fraction
        )
        score = max(
            0.0,
            min(
                1.0,
                base
                - integrity_penalty
                - self._candidate_penalty(candidate),
            ),
        )

        reasons: list[str] = []
        if unknown_count:
            reasons.append(f"unknown_evidence={unknown_count}")
        if fingerprint_mismatches:
            reasons.append(
                f"fingerprint_mismatch={fingerprint_mismatches}"
            )
        if identity_mismatches:
            reasons.append(f"identity_mismatch={identity_mismatches}")
        if stale_count:
            reasons.append(f"stale_evidence={stale_count}")
        if low_confidence_count:
            reasons.append(
                f"low_confidence_evidence={low_confidence_count}"
            )
        if contradictions:
            reasons.append(
                f"contradiction_count={len(contradictions)}"
            )
        reasons.extend(
            (
                f"custody_fraction={custody_fraction:.3f}",
                f"fingerprint_fraction={fingerprint_fraction:.3f}",
                f"source_diversity={source_diversity:.3f}",
            )
        )

        rejected = bool(
            unknown_count
            or fingerprint_mismatches
            or identity_mismatches
            or stale_count
            or low_confidence_count
            or contradictions
        )
        return self._host_report(
            candidate,
            score=score,
            custody_fraction=custody_fraction,
            fingerprint_fraction=fingerprint_fraction,
            identity_fraction=identity_fraction,
            source_diversity=source_diversity,
            confidence_quality=confidence_quality,
            contradiction_count=len(contradictions),
            contradiction_rate=contradiction_rate,
            known_evidence_count=known_count,
            unknown_evidence_count=unknown_count,
            fingerprint_mismatch_count=fingerprint_mismatches,
            identity_mismatch_count=identity_mismatches,
            stale_evidence_count=stale_count,
            rejected=rejected,
            reasons=tuple(reasons),
        )

    def _host_report(
        self,
        candidate: CandidateProposal,
        *,
        score: float,
        custody_fraction: float,
        fingerprint_fraction: float,
        identity_fraction: float,
        source_diversity: float,
        confidence_quality: float,
        contradiction_count: int,
        contradiction_rate: float,
        known_evidence_count: int,
        unknown_evidence_count: int,
        fingerprint_mismatch_count: int,
        identity_mismatch_count: int,
        stale_evidence_count: int,
        rejected: bool,
        reasons: tuple[str, ...],
    ) -> HostCandidateAdjudicationReport:
        payload = {
            "candidate": candidate.fingerprint,
            "score": score,
            "custody_fraction": custody_fraction,
            "fingerprint_fraction": fingerprint_fraction,
            "identity_fraction": identity_fraction,
            "source_diversity": source_diversity,
            "confidence_quality": confidence_quality,
            "contradiction_count": contradiction_count,
            "contradiction_rate": contradiction_rate,
            "known_evidence_count": known_evidence_count,
            "unknown_evidence_count": unknown_evidence_count,
            "fingerprint_mismatch_count": fingerprint_mismatch_count,
            "identity_mismatch_count": identity_mismatch_count,
            "stale_evidence_count": stale_evidence_count,
            "rejected": rejected,
            "reasons": reasons,
            "policy": self.policy.fingerprint,
            "ledger": self.ledger.fingerprint,
        }
        return HostCandidateAdjudicationReport(
            candidate_id=candidate.candidate_id,
            score=score,
            custody_fraction=custody_fraction,
            fingerprint_fraction=fingerprint_fraction,
            identity_fraction=identity_fraction,
            source_diversity=source_diversity,
            confidence_quality=confidence_quality,
            contradiction_count=contradiction_count,
            contradiction_rate=contradiction_rate,
            known_evidence_count=known_evidence_count,
            unknown_evidence_count=unknown_evidence_count,
            fingerprint_mismatch_count=fingerprint_mismatch_count,
            identity_mismatch_count=identity_mismatch_count,
            stale_evidence_count=stale_evidence_count,
            rejected=rejected,
            reasons=reasons,
            policy_fingerprint=self.policy.fingerprint,
            ledger_fingerprint=self.ledger.fingerprint,
            fingerprint=stable_fingerprint(payload),
        )

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
