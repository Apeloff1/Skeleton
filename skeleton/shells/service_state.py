"""State machine for the shell execution service facade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable


class ShellServicePhase(str, Enum):
    NEW = "new"
    STARTING = "starting"
    READY = "ready"
    DRAINING = "draining"
    MAINTENANCE = "maintenance"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


_ALLOWED = {
    ShellServicePhase.NEW: {ShellServicePhase.STARTING, ShellServicePhase.FAILED},
    ShellServicePhase.STARTING: {ShellServicePhase.READY, ShellServicePhase.FAILED, ShellServicePhase.STOPPING},
    ShellServicePhase.READY: {
        ShellServicePhase.DRAINING,
        ShellServicePhase.MAINTENANCE,
        ShellServicePhase.STOPPING,
        ShellServicePhase.FAILED,
    },
    ShellServicePhase.DRAINING: {ShellServicePhase.READY, ShellServicePhase.STOPPING, ShellServicePhase.FAILED},
    ShellServicePhase.MAINTENANCE: {ShellServicePhase.READY, ShellServicePhase.STOPPING, ShellServicePhase.FAILED},
    ShellServicePhase.STOPPING: {ShellServicePhase.STOPPED, ShellServicePhase.FAILED},
    ShellServicePhase.STOPPED: set(),
    ShellServicePhase.FAILED: {ShellServicePhase.STOPPING, ShellServicePhase.STOPPED},
}


@dataclass(frozen=True)
class ServiceTransition:
    sequence: int
    previous: ShellServicePhase
    current: ShellServicePhase
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


class ShellServiceState:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_history: int = 1000,
    ) -> None:
        if isinstance(max_history, bool) or not isinstance(max_history, int) or max_history <= 0:
            raise ValueError("max_history must be a positive integer")
        self._clock = clock
        self.max_history = max_history
        self._phase = ShellServicePhase.NEW
        self._history: list[ServiceTransition] = []
        self._lock = threading.RLock()

    @property
    def phase(self) -> ShellServicePhase:
        with self._lock:
            return self._phase

    def transition(self, target: ShellServicePhase, *, reason: str = "") -> ServiceTransition:
        target = ShellServicePhase(target)
        if not isinstance(reason, str) or len(reason) > 512 or "\x00" in reason:
            raise ValueError("invalid service transition reason")
        with self._lock:
            if target not in _ALLOWED[self._phase]:
                raise RuntimeError(f"invalid shell service transition {self._phase.value}->{target.value}")
            transition = ServiceTransition(
                len(self._history) + 1,
                self._phase,
                target,
                self._clock(),
                reason,
            )
            self._phase = target
            self._history.append(transition)
            if len(self._history) > self.max_history:
                self._history = self._history[-self.max_history :]
            return transition

    def history(self) -> tuple[ServiceTransition, ...]:
        with self._lock:
            return tuple(self._history)

    def ready(self) -> bool:
        return self.phase is ShellServicePhase.READY
