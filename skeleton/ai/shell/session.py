"""Explicit state machine for one AI-assisted shell interaction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable

from skeleton.shells.ai.types import AIIntent, AIPlanProposal


class AISessionPhase(str, Enum):
    NEW = "new"
    PLANNING = "planning"
    PROPOSED = "proposed"
    REVIEW = "review"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    DENIED = "denied"
    CANCELLED = "cancelled"
    FAILED = "failed"


_ALLOWED = {
    AISessionPhase.NEW: {AISessionPhase.PLANNING, AISessionPhase.CANCELLED},
    AISessionPhase.PLANNING: {AISessionPhase.PROPOSED, AISessionPhase.FAILED, AISessionPhase.CANCELLED},
    AISessionPhase.PROPOSED: {AISessionPhase.REVIEW, AISessionPhase.DENIED, AISessionPhase.CANCELLED},
    AISessionPhase.REVIEW: {AISessionPhase.APPROVED, AISessionPhase.DENIED, AISessionPhase.CANCELLED},
    AISessionPhase.APPROVED: {AISessionPhase.EXECUTING, AISessionPhase.CANCELLED},
    AISessionPhase.EXECUTING: {AISessionPhase.VERIFYING, AISessionPhase.FAILED},
    AISessionPhase.VERIFYING: {AISessionPhase.COMPLETE, AISessionPhase.FAILED},
    AISessionPhase.COMPLETE: set(),
    AISessionPhase.DENIED: set(),
    AISessionPhase.CANCELLED: set(),
    AISessionPhase.FAILED: set(),
}


@dataclass(frozen=True)
class AISessionTransition:
    sequence: int
    previous: AISessionPhase
    current: AISessionPhase
    observed_at: float
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "previous": self.previous.value,
            "current": self.current.value,
            "observed_at": self.observed_at,
            "reason": self.reason,
        }


class AIShellSession:
    def __init__(
        self,
        session_id: str,
        intent: AIIntent,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_history: int = 256,
    ) -> None:
        if not session_id or len(session_id) > 160:
            raise ValueError("invalid AI session_id")
        if max_history <= 0:
            raise ValueError("max_history must be positive")
        self.session_id = session_id
        self.intent = intent
        self._clock = clock
        self.max_history = max_history
        self._phase = AISessionPhase.NEW
        self._proposal: AIPlanProposal | None = None
        self._history: list[AISessionTransition] = []
        self._lock = threading.RLock()

    @property
    def phase(self) -> AISessionPhase:
        with self._lock:
            return self._phase

    @property
    def proposal(self) -> AIPlanProposal | None:
        with self._lock:
            return self._proposal

    def set_proposal(self, proposal: AIPlanProposal) -> None:
        with self._lock:
            if self._phase is not AISessionPhase.PLANNING:
                raise RuntimeError("proposal may only be set while planning")
            if proposal.intent_id != self.intent.intent_id:
                raise ValueError("proposal intent mismatch")
            self._proposal = proposal
            self.transition(AISessionPhase.PROPOSED)

    def transition(self, target: AISessionPhase, *, reason: str = "") -> AISessionTransition:
        target = AISessionPhase(target)
        if len(reason) > 512:
            raise ValueError("AI session transition reason too long")
        with self._lock:
            if target not in _ALLOWED[self._phase]:
                raise RuntimeError(
                    f"invalid AI session transition {self._phase.value}->{target.value}"
                )
            item = AISessionTransition(
                len(self._history) + 1,
                self._phase,
                target,
                self._clock(),
                reason,
            )
            self._phase = target
            self._history.append(item)
            if len(self._history) > self.max_history:
                self._history = self._history[-self.max_history :]
            return item

    def history(self) -> tuple[AISessionTransition, ...]:
        with self._lock:
            return tuple(self._history)
