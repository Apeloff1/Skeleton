"""Co-coding sessions — Jeeves collaborates on a pipeline in real time.

The co-coding session is the headline Jeeves mode: a bounded, staged
collaboration where Jeeves and the user build one pipeline artefact
together. The session owns the contract:

  - **Stages** advance only when the current stage's acceptance check
    passes; Jeeves proposes, the user (or a validator) disposes.
  - **Scaffolding decays** with demonstrated competence: hint density drops
    as consecutive successful stages accumulate (the learning-stages model
    from the product, executable).
  - **Everything is an event** — stage transitions, hint level changes, and
    completion land on the bus so the dashboard and the dream engine see
    the same session history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.errors import SessionError
from skeleton.kernel.events import DomainEvent, EventBus


class SkillLevel(Enum):
    ONBOARDING = auto()
    FOUNDATION = auto()
    GROWTH = auto()
    MASTERY = auto()

    @property
    def hint_density(self) -> float:
        """Fraction of stages where Jeeves volunteers a hint unprompted."""
        return {
            SkillLevel.ONBOARDING: 1.0,
            SkillLevel.FOUNDATION: 0.7,
            SkillLevel.GROWTH: 0.4,
            SkillLevel.MASTERY: 0.1,
        }[self]


@dataclass
class Stage:
    """One step of the collaboration with its acceptance check."""
    name: str
    prompt: str
    accept: Callable[[Any], bool]
    hint: str = ""
    attempts: int = 0


@dataclass
class CoCodingSession:
    session_id: str
    user_id: str
    pipeline: str                       # "npc", "game_logic", "animation"
    skill: SkillLevel
    stages: List[Stage]
    current: int = 0
    artefact: Dict[str, Any] = field(default_factory=dict)
    consecutive_successes: int = 0
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    @property
    def active(self) -> bool:
        return self.completed_at is None


class CoCodingOrchestrator:
    """Runs co-coding sessions against the pipeline surface."""

    MAX_ATTEMPTS_PER_STAGE = 5

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._sessions: Dict[str, CoCodingSession] = {}
        self._bus = bus

    def start(
        self,
        session_id: str,
        user_id: str,
        pipeline: str,
        skill: SkillLevel,
        stages: List[Stage],
    ) -> CoCodingSession:
        if session_id in self._sessions and self._sessions[session_id].active:
            raise SessionError(
                "session already active",
                context={"session_id": session_id},
            )
        if not stages:
            raise SessionError("a session needs at least one stage")
        session = CoCodingSession(
            session_id=session_id, user_id=user_id, pipeline=pipeline,
            skill=skill, stages=stages,
        )
        self._sessions[session_id] = session
        self._emit("jeeves.cocoding.started", session)
        return session

    def submit(self, session_id: str, work: Any) -> Dict[str, Any]:
        """
        Submit work for the current stage. Returns the outcome: accepted
        (and advanced?), a hint when due, or a rejection with attempts left.
        """
        session = self._require_active(session_id)
        stage = session.stages[session.current]
        stage.attempts += 1

        if stage.accept(work):
            session.consecutive_successes += 1
            session.artefact[stage.name] = work
            advanced = self._advance(session)
            self._emit("jeeves.cocoding.stage_accepted", session,
                       {"stage": stage.name, "advanced": advanced})
            return {
                "accepted": True,
                "advanced": advanced,
                "completed": not session.active,
                "stage": stage.name,
                "hint": None,
            }

        session.consecutive_successes = 0
        attempts_left = self.MAX_ATTEMPTS_PER_STAGE - stage.attempts
        if attempts_left <= 0:
            self._emit("jeeves.cocoding.stage_failed", session,
                       {"stage": stage.name})
            raise SessionError(
                "stage attempts exhausted",
                context={"session_id": session_id, "stage": stage.name},
            )
        hint = stage.hint if self._hint_due(session) else None
        self._emit("jeeves.cocoding.stage_rejected", session,
                   {"stage": stage.name, "attempts_left": attempts_left})
        return {
            "accepted": False,
            "advanced": False,
            "completed": False,
            "stage": stage.name,
            "hint": hint,
            "attempts_left": attempts_left,
        }

    def _advance(self, session: CoCodingSession) -> bool:
        if session.current + 1 < len(session.stages):
            session.current += 1
            return True
        session.completed_at = time.time()
        self._emit("jeeves.cocoding.completed", session,
                   {"duration_s": session.completed_at - session.started_at})
        return False

    def _hint_due(self, session: CoCodingSession) -> bool:
        """Scaffold decay: fewer unprompted hints as successes accumulate."""
        density = session.skill.hint_density
        decay = 1.0 / (1.0 + session.consecutive_successes)
        return (density * decay) >= 0.5

    def _require_active(self, session_id: str) -> CoCodingSession:
        session = self._sessions.get(session_id)
        if session is None or not session.active:
            raise SessionError(
                "no active session",
                context={"session_id": session_id},
            )
        return session

    def _emit(self, topic: str, session: CoCodingSession,
              extra: Optional[Dict[str, Any]] = None) -> None:
        if not self._bus:
            return
        payload: Dict[str, Any] = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "pipeline": session.pipeline,
            "stage_index": session.current,
        }
        if extra:
            payload.update(extra)
        self._bus.publish(
            DomainEvent(topic=topic, payload=payload,
                        correlation_id=f"ccs_{session.session_id}")
        )

    def stats(self) -> Dict[str, Any]:
        active = sum(1 for s in self._sessions.values() if s.active)
        return {"sessions": len(self._sessions), "active": active,
                "completed": len(self._sessions) - active}
