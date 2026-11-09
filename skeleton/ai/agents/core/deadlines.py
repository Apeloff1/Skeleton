"""Task deadline tracker — watch expiry per scheduled unit."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from skeleton.kernel.errors import SchedulingError


class DeadlineError(SchedulingError):
    code = "AGT.DEADLINES"


@dataclass
class DeadlineRecord:
    task_id: str
    due_at: float
    cancelled: bool = False


class DeadlineTracker:
    """Registry of due times per task; sweep() returns expired ids."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.monotonic
        self._records: Dict[str, DeadlineRecord] = {}

    def register(self, task_id: str, ttl_s: float) -> None:
        self._records[task_id] = DeadlineRecord(
            task_id=task_id, due_at=self._now() + ttl_s
        )

    def cancel(self, task_id: str) -> None:
        record = self._records.get(task_id)
        if record is None:
            raise DeadlineError("unknown task", context={"task": task_id})
        record.cancelled = True

    def sweep(self) -> Tuple[str, ...]:
        now = self._now()
        expired = [
            r.task_id
            for r in self._records.values()
            if not r.cancelled and r.due_at <= now
        ]
        return tuple(expired)

    def remaining(self, task_id: str) -> float:
        record = self._records.get(task_id)
        if record is None:
            raise DeadlineError("unknown task", context={"task": task_id})
        return max(0.0, record.due_at - self._now())
