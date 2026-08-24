"""Socratic engine — the questioning core of the immersive tutor.

Jeeves doesn't lecture; he asks. The Socratic engine manages that dialogue
as a formal structure: a misconception model per learner, a question
selection policy, and a move taxonomy (clarify, probe evidence, probe
assumptions, challenge, synthesise). The engine tracks which moves landed
and adapts: a learner who resolves challenges quickly gets deeper
challenges; one who stalls gets decomposition instead.

Design laws
-----------
- The engine never states the answer. Moves only *question*; explanation
  is the learner's job. This is the whole point of the method.
- The misconception model is explicit: beliefs are (claim, confidence)
  pairs, and a move is chosen to target the highest-confidence belief the
  engine has evidence against.
- Everything is per-learner state, so one engine serves a cohort with
  independent dialogues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus


class SocraticMove(Enum):
    CLARIFY = auto()          # "What do you mean by X?"
    PROBE_EVIDENCE = auto()   # "What makes you think that?"
    PROBE_ASSUMPTION = auto() # "What are you taking for granted?"
    CHALLENGE = auto()        # "But if X, wouldn't Y follow?"
    DECOMPOSE = auto()        # "Can we split that into parts?"
    SYNTHESISE = auto()       # "How do these two answers fit together?"


@dataclass
class Belief:
    """One learner claim the engine is tracking."""
    claim: str
    confidence: float = 0.5      # learner's stated confidence, 0–1
    challenged: int = 0
    resolved: bool = False


@dataclass
class Turn:
    move: SocraticMove
    question: str
    target_claim: Optional[str]


@dataclass
class Dialogue:
    learner_id: str
    topic: str
    beliefs: List[Belief] = field(default_factory=list)
    turns: List[Turn] = field(default_factory=list)
    stalls: int = 0


class SocraticEngine:
    """Chooses the next Socratic move for a learner dialogue."""

    STALL_LIMIT = 2              # stalls before switching to DECOMPOSE
    RESOLVE_THRESHOLD = 2        # challenges survived -> belief resolved

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._dialogues: Dict[str, Dialogue] = {}
        self._bus = bus

    def open(self, learner_id: str, topic: str) -> Dialogue:
        dialogue = Dialogue(learner_id=learner_id, topic=topic)
        self._dialogues[learner_id] = dialogue
        return dialogue

    def register_belief(self, learner_id: str, claim: str,
                        confidence: float = 0.5) -> Belief:
        belief = Belief(claim=claim, confidence=max(0.0, min(1.0, confidence)))
        self._require(learner_id).beliefs.append(belief)
        return belief

    def next_move(self, learner_id: str) -> Turn:
        """
        Pick the move targeting the highest-confidence unresolved belief.
        Move choice: DECOMPOSE if the learner is stalling, CHALLENGE a
        high-confidence belief, PROBE_ASSUMPTION mid-confidence, otherwise
        PROBE_EVIDENCE. CLARIFY when there's nothing to target yet.
        """
        dialogue = self._require(learner_id)
        open_beliefs = [b for b in dialogue.beliefs if not b.resolved]

        if not open_beliefs:
            turn = Turn(SocraticMove.CLARIFY,
                        f"What do you understand {dialogue.topic} to mean?", None)
        else:
            target = max(open_beliefs, key=lambda b: b.confidence)
            if dialogue.stalls >= self.STALL_LIMIT:
                move, q = SocraticMove.DECOMPOSE, (
                    f"Can you break \"{target.claim}\" into its smallest parts "
                    "and tell me which one you're least sure of?")
            elif target.confidence >= 0.7:
                move, q = SocraticMove.CHALLENGE, (
                    f"If \"{target.claim}\" were exactly wrong, what would you "
                    "expect to observe instead?")
            elif target.confidence >= 0.4:
                move, q = SocraticMove.PROBE_ASSUMPTION, (
                    f"What has to be true for \"{target.claim}\" to hold?")
            else:
                move, q = SocraticMove.PROBE_EVIDENCE, (
                    f"What's the strongest evidence you have for \"{target.claim}\"?")
            turn = Turn(move, q, target.claim)

        dialogue.turns.append(turn)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="jeeves.socratic.move",
                    payload={
                        "learner": learner_id,
                        "move": turn.move.name,
                        "target": turn.target_claim,
                        "turn": len(dialogue.turns),
                    },
                    correlation_id=f"soc_{learner_id}",
                )
            )
        return turn

    def report_outcome(self, learner_id: str, *,
                       resolved: bool, stalled: bool = False) -> None:
        """Feed the learner's response back into the model."""
        dialogue = self._require(learner_id)
        if stalled:
            dialogue.stalls += 1
        else:
            dialogue.stalls = 0
        open_beliefs = [b for b in dialogue.beliefs if not b.resolved]
        if not open_beliefs:
            return
        target = max(open_beliefs, key=lambda b: b.confidence)
        if resolved:
            target.challenged += 1
            target.confidence *= 0.9   # survived challenges decay overconfidence
            if target.challenged >= self.RESOLVE_THRESHOLD:
                target.resolved = True
                if self._bus:
                    self._bus.publish(
                        DomainEvent(
                            topic="jeeves.socratic.belief_resolved",
                            payload={"learner": learner_id, "claim": target.claim},
                            correlation_id=f"soc_{learner_id}",
                        )
                    )
        else:
            target.confidence = min(1.0, target.confidence + 0.05)

    def mastery(self, learner_id: str) -> Dict[str, Any]:
        dialogue = self._require(learner_id)
        resolved = sum(1 for b in dialogue.beliefs if b.resolved)
        return {
            "learner": learner_id,
            "beliefs_tracked": len(dialogue.beliefs),
            "resolved": resolved,
            "mastery_ratio": resolved / len(dialogue.beliefs) if dialogue.beliefs else 0.0,
            "turns": len(dialogue.turns),
            "stalls": dialogue.stalls,
        }

    def _require(self, learner_id: str) -> Dialogue:
        if learner_id not in self._dialogues:
            raise KeyError(f"no open Socratic dialogue for {learner_id!r}")
        return self._dialogues[learner_id]
