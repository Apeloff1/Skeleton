"""Lifecycle state machine for the long-lived AI shell service."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable


class AIServicePhase(str, Enum):
    NEW = "new"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"
    DRAINING = "draining"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


_ALLOWED = {
    AIServicePhase.NEW: {AIServicePhase.STARTING, AIServicePhase.FAILED},
    AIServicePhase.STARTING: {AIServicePhase.READY, AIServicePhase.DEGRADED, AIServicePhase.FAILED},
    AIServicePhase.READY: {
        AIServicePhase.DEGRADED,
        AIServicePhase.MAINTENANCE,
        AIServicePhase.DRAINING,
        AIServicePhase.STOPPING,
        AIServicePhase.FAILED,
    },
    AIServicePhase.DEGRADED: {
        AIServicePhase.READY,
        AIServicePhase.MAINTENANCE,
        AIServicePhase.DRAINING,
        AIServicePhase.STOPPING,
        AIServicePhase.FAILED,
    },
    AIServicePhase.MAINTENANCE: {
        AIServicePhase.READY,
        AIServicePhase.DEGRADED,
        AIServicePhase.DRAINING,
        AIServicePhase.STOPPING,
        AIServicePhase.FAILED,
    },
    AIServicePhase.DRAINING: {
        AIServicePhase.READY,
        AIServicePhase.STOPPING,
        AIServicePhase.FAILED,
    },
    AIServicePhase.STOPPING: {AIServicePhase.STOPPED, AIServicePhase.FAILED},
    AIServicePhase.STOPPED: set(),
    AIServicePhase.FAILED: {AIServicePhase.STOPPING, AIServicePhase.STOPPED},
}


@dataclass(frozen=True)
class AIServiceTransition:
    sequence: int
    previous: AIServicePhase
    current: AIServicePhase
    observed_at: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "previous": self.previous.value,
            "current": self.current.value,
            "observed_at": self.observed_at,
            "reason": self.reason,
        }


class AIServiceState:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._phase = AIServicePhase.NEW
        self._history: list[AIServiceTransition] = []
        self._lock = threading.RLock()

    @property
    def phase(self) -> AIServicePhase:
        with self._lock:
            return self._phase

    @property
    def reason(self) -> str:
        with self._lock:
            if not self._history:
                return ""
            return self._history[-1].reason

    def ready(self) -> bool:
        return self.phase is AIServicePhase.READY

    def transition(self, target: AIServicePhase, *, reason: str = "") -> AIServiceTransition:
        target = AIServicePhase(target)
        if len(reason) > 1024:
            raise ValueError("AI service transition reason too long")
        with self._lock:
            if target not in _ALLOWED[self._phase]:
                raise RuntimeError(
                    f"invalid AI service transition {self._phase.value}->{target.value}"
                )
            item = AIServiceTransition(
                len(self._history) + 1,
                self._phase,
                target,
                self._clock(),
                reason,
            )
            self._phase = target
            self._history.append(item)
            return item

    def history(self) -> tuple[AIServiceTransition, ...]:
        with self._lock:
            return tuple(self._history)
