"""Explicit evidence, belief state, contradiction, and misconception lifecycle."""
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
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.evidence_id in self.supersedes:
            raise ValueError("evidence cannot supersede itself")
        if len(set(self.supersedes)) != len(self.supersedes):
            raise ValueError("supersedes contains duplicate evidence ids")

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
    evidence: dict[str, EpistemicEvidence] = field(default_factory=dict)
    beliefs: dict[str, BeliefState] = field(default_factory=dict)
    misconceptions: dict[str, MisconceptionStage] = field(default_factory=dict)

    def observe(self, item: EpistemicEvidence) -> EpistemicUpdate:
        old = self.evidence.get(item.evidence_id)
        if old is not None and old != item:
            raise ValueError(f"evidence id collision: {item.evidence_id}")
        for superseded_id in item.supersedes:
            if superseded_id not in self.evidence:
                raise ValueError(f"unknown superseded evidence: {superseded_id}")
            if self.evidence[superseded_id].claim != item.claim:
                raise ValueError("superseded evidence must concern the same claim")
        self.evidence[item.evidence_id] = item
        belief = self._recompute(item.claim)
        prior = self.beliefs.get(item.claim)
        self.beliefs[item.claim] = belief
        delta = belief.confidence - (prior.confidence if prior else 0.5)
        rationale = (
            ("supporting evidence increased belief",)
            if item.polarity is EvidencePolarity.SUPPORTS
            else ("refuting evidence decreased belief",)
            if item.polarity is EvidencePolarity.REFUTES
            else ("neutral evidence preserved belief",)
        )
        if belief.contradiction:
            rationale += ("support and refutation are simultaneously active",)
        if item.supersedes:
            rationale += (f"superseded evidence: {','.join(item.supersedes)}",)
        return EpistemicUpdate(belief, delta, belief.contradiction, rationale)

    def active_evidence(self, claim: str | None = None) -> tuple[EpistemicEvidence, ...]:
        superseded = {sid for item in self.evidence.values() for sid in item.supersedes}
        return tuple(
            item
            for item in self.evidence.values()
            if item.evidence_id not in superseded and (claim is None or item.claim == claim)
        )

    def supersede(self, evidence_id: str, *, replacement_id: str, strength: float | None = None) -> EpistemicUpdate:
        original = self.evidence.get(evidence_id)
        if original is None:
            raise KeyError(evidence_id)
        replacement = EpistemicEvidence(
            evidence_id=replacement_id,
            claim=original.claim,
            polarity=original.polarity,
            strength=original.strength if strength is None else strength,
            source_id=original.source_id,
            reliability=original.reliability,
            step=original.step + 1,
            supersedes=(evidence_id,),
        )
        return self.observe(replacement)

    def decay(self, *, current_step: int, half_life: int = 20):
        if half_life <= 0:
            raise ValueError("half_life must be positive")
        result = []
        for claim, belief in self.beliefs.items():
            age = max(0, current_step - belief.last_updated_step)
            factor = 0.5 ** (age / half_life)
            centered = 0.5 + (belief.confidence - 0.5) * factor
            updated = BeliefState(
                claim,
                centered,
                belief.support * factor,
                belief.refutation * factor,
                belief.evidence_ids,
                belief.last_updated_step,
                belief.contradiction,
            )
            self.beliefs[claim] = updated
            result.append(updated)
        return tuple(result)

    def mark_misconception(self, claim, stage):
        self.misconceptions[claim] = stage

    def repair_signal(self, claim):
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

    def contradictions(self):
        return tuple(b for b in self.beliefs.values() if b.contradiction)

    def _recompute(self, claim: str) -> BeliefState:
        active = self.active_evidence(claim)
        support = sum(e.weight for e in active if e.polarity is EvidencePolarity.SUPPORTS)
        refutation = sum(e.weight for e in active if e.polarity is EvidencePolarity.REFUTES)
        total = support + refutation
        raw = support / total if total else 0.5
        confidence = self._bounded_confidence(raw, support, refutation)
        prior = self.beliefs.get(claim)
        return BeliefState(
            claim=claim,
            confidence=confidence,
            support=support,
            refutation=refutation,
            evidence_ids=tuple(e.evidence_id for e in active),
            last_updated_step=max(
                (e.step for e in active),
                default=prior.last_updated_step if prior else 0,
            ),
            contradiction=support > 0 and refutation > 0,
        )

    @staticmethod
    def _bounded_confidence(raw, support, refutation):
        if support and refutation:
            conflict = min(support, refutation) / max(support, refutation)
            return min(raw, 0.95 - 0.35 * conflict)
        return max(0.05, min(0.95, raw))


def contradiction_matrix(evidence: Sequence[EpistemicEvidence]):
    by_claim = {}
    for item in evidence:
        by_claim.setdefault(item.claim, set()).add(item.polarity)
    return tuple(
        sorted(
            (claim, "support/refute")
            for claim, pol in by_claim.items()
            if EvidencePolarity.SUPPORTS in pol and EvidencePolarity.REFUTES in pol
        )
    )
