"""Host-side structural adjudication for Jeeves deliberation candidates.

This layer intentionally does not claim to verify factual truth. Candidate
proposals are concise decision summaries, not typed factual claims. Reusing the
full verification council here would therefore create misleading grounding
scores.

Instead, the adjudicator checks properties the host can actually verify before
ranking a candidate:

* every referenced evidence id exists in the run ledger;
* referenced fingerprints match authoritative ledger artifacts;
* evidence confidence and source diversity support the candidate confidence;
* evidence used by the candidate is not internally contradictory;
* high-confidence candidates without evidence are penalized rather than granted
  a neutral verifier score.

The resulting score is suitable for CandidateScorer.verifier. It is a
structural support score, never a substitute for step verification, grounding,
or the hardened runtime guard.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .deliberation import CandidateProposal
from .evidence import EvidenceLedger
from .types import AgentContractError, probability, stable_fingerprint


@dataclass(frozen=True, slots=True)
class CandidateAdjudication:
    candidate_id: str
    score: float
    custody_fraction: float
    fingerprint_fraction: float
    mean_evidence_confidence: float
    source_diversity: float
    confidence_alignment: float
    contradiction_rate: float
    evidence_count: int
    known_evidence_count: int
    contradiction_count: int
    reasons: tuple[str, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise AgentContractError("candidate_id must be non-empty")
        for name in (
            "score",
            "custody_fraction",
            "fingerprint_fraction",
            "mean_evidence_confidence",
            "source_diversity",
            "confidence_alignment",
            "contradiction_rate",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in (
            "evidence_count",
            "known_evidence_count",
            "contradiction_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be a non-negative integer")
        if self.known_evidence_count > self.evidence_count:
            raise AgentContractError("known_evidence_count exceeds evidence_count")
        object.__setattr__(
            self,
            "reasons",
            tuple(
                str(reason).strip()[:2048]
                for reason in self.reasons
                if str(reason).strip()
            ),
        )


class HostCandidateAdjudicator:
    """Score candidate support using only host-verifiable evidence structure."""

    def __init__(self, ledger: EvidenceLedger) -> None:
        if not isinstance(ledger, EvidenceLedger):
            raise TypeError("ledger must be EvidenceLedger")
        self.ledger = ledger

    def score(self, candidate: CandidateProposal) -> float:
        return self.adjudicate(candidate).score

    def adjudicate(self, candidate: CandidateProposal) -> CandidateAdjudication:
        if not isinstance(candidate, CandidateProposal):
            raise TypeError("candidate must be CandidateProposal")

        refs = tuple(candidate.evidence)
        if not refs:
            score = max(0.05, min(0.35, 0.35 - 0.20 * candidate.confidence))
            reasons = (
                "candidate has no bound evidence; structural verifier is conservative",
            )
            fingerprint = stable_fingerprint(
                {
                    "candidate": candidate.fingerprint,
                    "ledger": self.ledger.fingerprint,
                    "score": score,
                    "evidence": (),
                    "contradictions": (),
                }
            )
            return CandidateAdjudication(
                candidate_id=candidate.candidate_id,
                score=score,
                custody_fraction=0.0,
                fingerprint_fraction=0.0,
                mean_evidence_confidence=0.0,
                source_diversity=0.0,
                confidence_alignment=max(0.0, 1.0 - candidate.confidence),
                contradiction_rate=0.0,
                evidence_count=0,
                known_evidence_count=0,
                contradiction_count=0,
                reasons=reasons,
                fingerprint=fingerprint,
            )

        known = []
        fingerprint_matches = 0
        confidence_values: list[float] = []
        sources: set[str] = set()
        unknown_ids: list[str] = []
        mismatch_ids: list[str] = []
        evidence_ids = [ref.evidence_id for ref in refs]

        for ref in refs:
            artifact = self.ledger.get(ref.evidence_id)
            if artifact is None:
                unknown_ids.append(ref.evidence_id)
                continue
            known.append(artifact)
            sources.add(artifact.source)
            confidence_values.append(min(ref.confidence, artifact.confidence))
            if artifact.fingerprint == ref.fingerprint:
                fingerprint_matches += 1
            else:
                mismatch_ids.append(ref.evidence_id)

        custody_fraction = len(known) / len(refs)
        fingerprint_fraction = fingerprint_matches / len(refs)
        mean_confidence = (
            statistics.fmean(confidence_values) if confidence_values else 0.0
        )
        source_diversity = len(sources) / len(known) if known else 0.0
        confidence_alignment = max(
            0.0,
            1.0 - abs(candidate.confidence - mean_confidence),
        )

        contradictions = self.ledger.contradictions_for(evidence_ids)
        contradiction_rate = min(
            1.0,
            2.0 * len(contradictions) / max(1, len(refs)),
        )

        score = (
            0.28 * custody_fraction
            + 0.24 * fingerprint_fraction
            + 0.20 * mean_confidence
            + 0.10 * source_diversity
            + 0.18 * confidence_alignment
            - 0.25 * (1.0 - custody_fraction)
            - 0.25 * (1.0 - fingerprint_fraction)
            - 0.45 * contradiction_rate
        )
        score = max(0.0, min(1.0, score))

        reasons: list[str] = [
            f"custody={custody_fraction:.3f}",
            f"fingerprint_integrity={fingerprint_fraction:.3f}",
            f"evidence_confidence={mean_confidence:.3f}",
            f"source_diversity={source_diversity:.3f}",
            f"confidence_alignment={confidence_alignment:.3f}",
            f"contradiction_rate={contradiction_rate:.3f}",
        ]
        if unknown_ids:
            reasons.append("unknown_evidence=" + ",".join(sorted(unknown_ids)))
        if mismatch_ids:
            reasons.append(
                "fingerprint_mismatch=" + ",".join(sorted(mismatch_ids))
            )
        if contradictions:
            reasons.append(
                "contradictions="
                + ",".join(item.contradiction_id for item in contradictions)
            )

        fingerprint = stable_fingerprint(
            {
                "candidate": candidate.fingerprint,
                "ledger": self.ledger.fingerprint,
                "score": score,
                "custody": custody_fraction,
                "fingerprint_fraction": fingerprint_fraction,
                "confidence": mean_confidence,
                "source_diversity": source_diversity,
                "alignment": confidence_alignment,
                "contradictions": [
                    (item.contradiction_id, item.left_id, item.right_id)
                    for item in contradictions
                ],
                "unknown": sorted(unknown_ids),
                "mismatch": sorted(mismatch_ids),
            }
        )
        return CandidateAdjudication(
            candidate_id=candidate.candidate_id,
            score=score,
            custody_fraction=custody_fraction,
            fingerprint_fraction=fingerprint_fraction,
            mean_evidence_confidence=mean_confidence,
            source_diversity=source_diversity,
            confidence_alignment=confidence_alignment,
            contradiction_rate=contradiction_rate,
            evidence_count=len(refs),
            known_evidence_count=len(known),
            contradiction_count=len(contradictions),
            reasons=tuple(reasons),
            fingerprint=fingerprint,
        )


__all__ = [
    "CandidateAdjudication",
    "HostCandidateAdjudicator",
]
