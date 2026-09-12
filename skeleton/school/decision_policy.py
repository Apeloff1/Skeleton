"""Evidence-aware arbitration for Jeeves control decisions.

This layer turns epistemic state into bounded policy signals. It does not call
models and does not choose arbitrary actions: it produces a deterministic
recommendation plus explicit reasons that can be written to the decision
ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from skeleton.school.knowledge import KnowledgeState


class ArbitrationAction(str, Enum):
    RETEACH = "reteach"
    RETRIEVE = "retrieve"
    PRACTICE = "practice"
    CHALLENGE = "challenge"
    TRANSFER = "transfer"
    REFLECT = "reflect"
    PAUSE = "pause"


@dataclass(frozen=True)
class EvidenceSignal:
    name: str
    value: float
    reliability: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError("signal value must be in [0, 1]")
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("signal reliability must be in [0, 1]")

    @property
    def effective(self) -> float:
        return self.value * self.reliability


@dataclass(frozen=True)
class ArbitrationResult:
    action: ArbitrationAction
    confidence: float
    rationale: tuple[str, ...]
    signals: tuple[EvidenceSignal, ...]


def arbitrate(
    state: KnowledgeState,
    skill_id: str,
    *,
    signals: Sequence[EvidenceSignal] = (),
    energy: float = 1.0,
    recent_failure: bool = False,
    transfer_ready: bool = False,
) -> ArbitrationResult:
    """Select the least risky useful next action from observable evidence."""
    if not skill_id:
        raise ValueError("skill_id cannot be empty")
    energy = max(0.0, min(1.0, energy))
    mastery = state.mastery(skill_id)
    contradiction = any(s.name == "contradiction" and s.effective >= 0.5 for s in signals)
    retention = next((s.effective for s in signals if s.name == "retention"), mastery)
    independence = next((s.effective for s in signals if s.name == "independence"), mastery)

    reasons: list[str] = []
    if skill_id in state.misconceptions or contradiction:
        reasons.append("repair conflicting or incorrect belief before escalation")
        action = ArbitrationAction.RETEACH
    elif energy < 0.25:
        reasons.append("energy budget is too low for high-load work")
        action = ArbitrationAction.PAUSE
    elif recent_failure or mastery < 0.4:
        reasons.append("recent evidence indicates a foundational gap")
        action = ArbitrationAction.PRACTICE
    elif transfer_ready and independence >= 0.7:
        reasons.append("mastery and independence support transfer")
        action = ArbitrationAction.TRANSFER
    elif mastery >= 0.85 and retention >= 0.75:
        reasons.append("strong mastery and retention support challenge")
        action = ArbitrationAction.CHALLENGE
    elif retention < 0.6:
        reasons.append("retention evidence calls for retrieval")
        action = ArbitrationAction.RETRIEVE
    else:
        reasons.append("continue deliberate practice at current difficulty")
        action = ArbitrationAction.PRACTICE

    confidence = min(1.0, max(0.0, 0.35 + 0.45 * mastery + 0.2 * (1.0 if signals else 0.0)))
    if contradiction:
        confidence *= 0.65
        reasons.append("decision confidence reduced because evidence conflicts")
    return ArbitrationResult(action, confidence, tuple(reasons), tuple(signals))
