"""Session tracker — interact logs, durations, fall-through for Jeeves.

CoCoding sessions expire in-memory; the tracker logs context
(session_id, start/at, ended, hints used, assessment events) so the
tutor can summarize durations by agent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.jeeves.feedback import FeedbackCollector
from skeleton.jeeves.pedagogy import Hint
from skeleton.jeeves.reflection import ReflectionBuilder


@dataclass
class SessionTracking:
    session_id: str
    mode: str
    started_at: float
    ended_at: Optional[float] = None
    hints_used: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return end - self.started_at


class SessionTracker:
    """Instrumentation of CoCoding sessions for reporting."""

    def __init__(
        self,
        *,
        reflection: Optional[ReflectionBuilder] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._now = clock or time.monotonic
        self._reflection = reflection or ReflectionBuilder()
        self._sessions: Dict[str, SessionTracking] = {}

    def register(self, session_id: str, mode: str = "tutor") -> SessionTracking:
        tracked = SessionTracking(
            session_id=session_id, mode=mode, started_at=self._now()
        )
        self._sessions[session_id] = tracked
        return tracked

    def record_event(self, session_id: str, name: str, **payload: Any) -> None:
        session = self._require(session_id)
        session.events.append({"name": name, **payload})

    def hint_used(self, session_id: str) -> None:
        session = self._require(session_id)
        session.hints_used += 1

    def end(self, session_id: str) -> SessionTracking:
        session = self._require(session_id)
        session.ended_at = self._now()
        return session

    def snapshot(self, session_id: str) -> Dict[str, Any]:
        session = self._require(session_id)
        return {
            "session": session.session_id,
            "mode": session.mode,
            "duration_s": round(session.duration_s, 3),
            "hints_used": session.hints_used,
            "event_count": len(session.events),
        }

    def _require(self, session_id: str) -> SessionTracking:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session
