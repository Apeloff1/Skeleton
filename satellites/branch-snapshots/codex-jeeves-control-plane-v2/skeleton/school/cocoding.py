"""Jeeves co-coding policy primitives.

Derived from Interesting-22's Jeeves co-coding protocol: collaborative ownership,
think-aloud guidance, graduated handoff, error-embracing debugging, and structured
session phases.  The module emits policy; it does not write code or depend on an
LLM/provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CodingPhase(str, Enum):
    UNDERSTAND = "understand"
    DESIGN = "design"
    IMPLEMENT = "implement"
    TEST = "test"
    REFLECT = "reflect"


class HandoffStage(str, Enum):
    DEMONSTRATE = "demonstrate"
    COMPLETE = "complete"
    REFINE = "refine"
    REVIEW = "review"
    INDEPENDENT = "independent"


class InteractionPattern(str, Enum):
    SUGGEST = "suggest"
    DISCOVER = "discover"
    EXPLORE = "explore"
    CORRECT = "correct"
    BRIDGE = "bridge"


@dataclass(frozen=True)
class CoCodingContext:
    phase: CodingPhase
    handoff: HandoffStage
    learner_stuck: bool = False
    learner_requested_code: bool = False
    recent_errors: int = 0
    understanding_confidence: float = 0.5


@dataclass(frozen=True)
class CoCodingAction:
    action: str
    pattern: InteractionPattern
    learner_owns_next_step: bool
    ask_before_writing: bool
    rationale: str


def choose_action(context: CoCodingContext) -> CoCodingAction:
    """Choose the next collaborative move without taking authorship away."""
    confidence = max(0.0, min(1.0, context.understanding_confidence))
    if context.phase is CodingPhase.UNDERSTAND:
        return CoCodingAction("clarify requirements and edge cases", InteractionPattern.EXPLORE, True, True, "understand before implementation")
    if context.phase is CodingPhase.DESIGN:
        return CoCodingAction("compare approaches and trade-offs", InteractionPattern.DISCOVER, True, True, "plan collaboratively before coding")
    if context.learner_stuck or context.recent_errors >= 2:
        return CoCodingAction("guide a debugging trace with a targeted hint", InteractionPattern.CORRECT, True, True, "use errors as learning evidence")
    if context.phase is CodingPhase.IMPLEMENT:
        if context.handoff in (HandoffStage.DEMONSTRATE, HandoffStage.COMPLETE):
            return CoCodingAction("show one small example, then hand back the next step", InteractionPattern.SUGGEST, True, not context.learner_requested_code, "fade scaffolding gradually")
        return CoCodingAction("ask the learner to choose and implement the next step", InteractionPattern.BRIDGE, True, True, "preserve learner ownership")
    if context.phase is CodingPhase.TEST:
        return CoCodingAction("design or inspect a test case together", InteractionPattern.DISCOVER, True, True, "testing consolidates reasoning")
    return CoCodingAction("review the solution and extract reusable lessons", InteractionPattern.BRIDGE, True, True, "reflection converts work into durable knowledge")


def next_handoff(current: HandoffStage, *, successful: bool, learner_explained: bool) -> HandoffStage:
    """Advance responsibility only when evidence supports reduced scaffolding."""
    if not successful or not learner_explained:
        return current
    order = list(HandoffStage)
    index = order.index(current)
    return order[min(index + 1, len(order) - 1)]
