"""SagaRegistry — named-step saga bookkeeping (gameforge-rs port).

Every long-running multi-step operation is a saga: visible, resumable, and
compensatable when a step fails. Steps are *named strings* only — no action
callables. Execution is owned by the caller; this registry owns truth.

Distinct from :mod:`skeleton.kernel.saga` (:class:`SagaLedger`), which drives
callable forward/compensation steps. Do not conflate the two.

Sibling source: ``/workspace/chaos-scout/gf-saga.rs``
(``gf-gameforge`` ``saga::SagaRegistry``).
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class StepStatus(str, Enum):
    PENDING = "Pending"
    DONE = "Done"
    COMPENSATED = "Compensated"
    FAILED = "Failed"


@dataclass
class NamedStep:
    name: str
    status: StepStatus = StepStatus.PENDING


@dataclass
class NamedSaga:
    id: str
    name: str
    steps: List[NamedStep]
    cursor: int = 0
    finished: bool = False
    failed: bool = False
    created: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "steps": [{"name": s.name, "status": s.status.value} for s in self.steps],
            "cursor": self.cursor,
            "finished": self.finished,
            "failed": self.failed,
            "created": self.created,
        }


class SagaRegistry:
    """Named-step saga registry (sync port of gf ``saga::SagaRegistry``)."""

    def __init__(self) -> None:
        self._sagas: Dict[str, NamedSaga] = {}
        self._lock = threading.RLock()

    def begin(self, name: str, steps: Sequence[str]) -> str:
        """Start a saga with named pending steps; returns saga id."""
        if not steps:
            raise ValueError("saga requires at least one named step")
        sid = str(uuid.uuid4())
        saga = NamedSaga(
            id=sid,
            name=str(name),
            steps=[NamedStep(name=str(s)) for s in steps],
        )
        with self._lock:
            self._sagas[sid] = saga
        return sid

    def complete_step(self, saga_id: str) -> Optional[bool]:
        """Mark the current step Done and advance. Returns finished flag, or None if missing."""
        with self._lock:
            saga = self._sagas.get(saga_id)
            if saga is None:
                return None
            if saga.finished or saga.failed:
                return saga.finished
            if saga.cursor < len(saga.steps):
                saga.steps[saga.cursor].status = StepStatus.DONE
                saga.cursor += 1
            if saga.cursor >= len(saga.steps):
                saga.finished = True
            return saga.finished

    def fail(self, saga_id: str) -> bool:
        """Fail current step; mark prior steps Compensated. Returns False if missing."""
        with self._lock:
            saga = self._sagas.get(saga_id)
            if saga is None:
                return False
            saga.failed = True
            if saga.cursor < len(saga.steps):
                saga.steps[saga.cursor].status = StepStatus.FAILED
            for i in range(saga.cursor - 1, -1, -1):
                saga.steps[i].status = StepStatus.COMPENSATED
            saga.finished = True
            return True

    def get(self, saga_id: str) -> Optional[NamedSaga]:
        with self._lock:
            return self._sagas.get(saga_id)

    def list(self) -> List[NamedSaga]:
        with self._lock:
            return list(self._sagas.values())

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            finished = sum(1 for s in self._sagas.values() if s.finished and not s.failed)
            failed = sum(1 for s in self._sagas.values() if s.failed)
            return {
                "total": len(self._sagas),
                "finished": finished,
                "failed": failed,
                "open": len(self._sagas) - finished - failed,
            }


__all__ = [
    "StepStatus",
    "NamedStep",
    "NamedSaga",
    "SagaRegistry",
]
