"""Evidence weighting and belief maintenance for Jeeves.

This layer deliberately does not decide *what is true* from a model response.
It manages competing evidence, confidence, contradiction, supersession and
misconception lifecycle so higher-level policies can make those decisions
explicitly and replayably.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class EvidencePolarity(str, Enum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    NEUTRAL = "neutral"


class MisconceptionStage(str, Enum):
    NONE = "none"
    DETECTED = "detected"
    HYPOTHESIS = "hypothesis"
    REPAIRING = "repairing"
    REPAIRED = "repaired"
    PERSISTENT = "persistent"


@dataclass(frozen=True)
class EpistemicEvidence:
    evidence_id: str
    claim: str
    polarity: EvidencePolarity
    strength: float = 1.0
    source_id: str = ""
    reliability: float = 1.0
    step: int = 0
    supersedes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (("strength", self.strength), ("reliability", self.reliability)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

    @property
    def weight(self) -> float:
        return self.strength * self.reliability


@dataclass(frozen=True)
class BeliefState:
    claim: str
    confidence: float
    support: float
    refutation: float
    evidence_ids: tuple[str, ...] = ()
    last_updated_step: int = 0
    contradiction: bool = False


@dataclass(frozen=True)
class EpistemicUpdate:
    belief: BeliefState
    confidence_delta: float
    contradiction: bool
    rationale: tuple[str, ...]


@dataclass
class EpistemicEngine:
    """Maintain deterministic claim beliefs from explicit evidence."""

    evidence: dict[str, EpistemicEvidence] = field(default_factory=dict)
    beliefs: dict[str, BeliefState] = field(default_factory=dict)
    misconceptions: dict[str, MisconceptionStage] = field(default_factory=dict)

    def observe(self, item: EpistemicEvidence) -> EpistemicUpdate:
        existing = self.evidence.get(item.evidence_id)
        if existing is not None and existing != item:
            raise ValueError(f"evidence id collision: {item.evidence_id}")
        self.evidence[item.evidence_id] = item
        prior = self.beliefs.get(item.claim)
        support = prior.support if prior else 0.0
        refutation = prior.refutation if prior else 0.0
        if item.polarity is EvidencePolarity.SUPPORTS:
            support += item.weight
        elif item.polarity is EvidencePolarity.REFUTES:
            refutation += item.weight
        total = support + refutation
        raw = support / total if total else 0.5
        confidence = self._bounded_confidence(raw, support, refutation)
        ids = tuple(dict.fromkeys((prior.evidence_ids if prior else ()) + (item.evidence_id,)))
        contradiction = support > 0 and refutation > 0
        belief = BeliefState(item.claim, confidence, support, refutation, ids, max(item.step, prior.last_updated_step if prior else 0), contradiction)
        self.beliefs[item.claim] = belief
        delta = confidence - (prior.confidence if prior else 0.5)
        rationale = ("supporting evidence increased belief",) if item.polarity is EvidencePolarity.SUPPORTS else ("refuting evidence decreased belief",) if item.polarity is EvidencePolarity.REFUTES else ("neutral evidence preserved belief",)
        if contradiction:
            rationale += ("support and refutation are simultaneously present",)
        return EpistemicUpdate(belief, delta, contradiction, rationale)

    def decay(self, *, current_step: int, half_life: int = 20) -> tuple[BeliefState, ...]:
        if half_life <= 0:
            raise ValueError("half_life must be positive")
        result: list[BeliefState] = []
        for claim, belief in self.beliefs.items():
            age = max(0, current_step - belief.last_updated_step)
            factor = 0.5 ** (age / half_life)
            centered = 0.5 + (belief.confidence - 0.5) * factor
            updated = BeliefState(claim, centered, belief.support * factor, belief.refutation * factor, belief.evidence_ids, belief.last_updated_step, belief.contradiction)
            self.beliefs[claim] = updated
            result.append(updated)
        return tuple(result)

    def mark_misconception(self, claim: str, stage: MisconceptionStage) -> None:
        self.misconceptions[claim] = stage

    def repair_signal(self, claim: str) -> str:
        stage = self.misconceptions.get(claim, MisconceptionStage.NONE)
        if stage is MisconceptionStage.PERSISTENT:
            return "reteach_with_new_representation"
        if stage in {MisconceptionStage.DETECTED, MisconceptionStage.HYPOTHESIS}:
            return "diagnose_and_test"
        if stage is MisconceptionStage.REPAIRING:
            return "verify_transfer"
        if stage is MisconceptionStage.REPAIRED:
            return "schedule_spaced_check"
        return "no_repair_required"

    def contradictions(self) -> tuple[BeliefState, ...]:
        return tuple(belief for belief in self.beliefs.values() if belief.contradiction)

    @staticmethod
    def _bounded_confidence(raw: float, support: float, refutation: float) -> float:
        # Mixed evidence should never produce artificial certainty.
        if support and refutation:
            conflict = min(support, refutation) / max(support, refutation)
            ceiling = 0.95 - 0.35 * conflict
            return min(raw, ceiling)
        return max(0.05, min(0.95, raw))


def contradiction_matrix(evidence: Sequence[EpistemicEvidence]) -> tuple[tuple[str, str], ...]:
    """Return claim pairs whose evidence directly conflicts."""
    by_claim: dict[str, set[EvidencePolarity]] = {}
    for item in evidence:
        by_claim.setdefault(item.claim, set()).add(item.polarity)
    return tuple(sorted((claim, "support/refute") for claim, polarities in by_claim.items() if EvidencePolarity.SUPPORTS in polarities and EvidencePolarity.REFUTES in polarities))
