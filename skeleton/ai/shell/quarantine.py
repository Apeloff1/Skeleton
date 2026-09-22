"""Quarantine registry for models, proposals, and tool contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable


class QuarantineTarget(str, Enum):
    MODEL = "model"
    PROPOSAL = "proposal"
    COMMAND = "command"


@dataclass(frozen=True)
class QuarantineRecord:
    target_type: QuarantineTarget
    target_id: str
    reason: str
    created_at: float
    expires_at: float | None
    actor: str

    @property
    def permanent(self) -> bool:
        return self.expires_at is None

    def active(self, now: float) -> bool:
        return self.expires_at is None or now < self.expires_at

    def to_dict(self) -> dict[str, object]:
        return {
            "target_type": self.target_type.value,
            "target_id": self.target_id,
            "reason": self.reason,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "actor": self.actor,
        }


class AIQuarantine:
    def __init__(
        self,
        *,
        max_records: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self._clock = clock
        self._items: dict[tuple[QuarantineTarget, str], QuarantineRecord] = {}
        self._lock = threading.RLock()

    def quarantine(
        self,
        target_type: QuarantineTarget,
        target_id: str,
        *,
        reason: str,
        actor: str,
        ttl_seconds: float | None = None,
    ) -> QuarantineRecord:
        target_type = QuarantineTarget(target_type)
        if not target_id or len(target_id) > 256:
            raise ValueError("invalid quarantine target")
        if not reason or len(reason) > 1024:
            raise ValueError("invalid quarantine reason")
        if not actor or len(actor) > 256:
            raise ValueError("invalid quarantine actor")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("quarantine TTL must be positive")
        with self._lock:
            key = (target_type, target_id)
            if key not in self._items and len(self._items) >= self.max_records:
                raise RuntimeError("AI quarantine capacity exhausted")
            now = self._clock()
            item = QuarantineRecord(
                target_type,
                target_id,
                reason,
                now,
                None if ttl_seconds is None else now + ttl_seconds,
                actor,
            )
            self._items[key] = item
            return item

    def active(self, target_type: QuarantineTarget, target_id: str) -> bool:
        with self._lock:
            item = self._items.get((QuarantineTarget(target_type), target_id))
            if item is None:
                return False
            if item.active(self._clock()):
                return True
            del self._items[(QuarantineTarget(target_type), target_id)]
            return False

    def release(self, target_type: QuarantineTarget, target_id: str) -> bool:
        with self._lock:
            return self._items.pop((QuarantineTarget(target_type), target_id), None) is not None

    def snapshot(self) -> tuple[QuarantineRecord, ...]:
        with self._lock:
            now = self._clock()
            expired = [key for key, item in self._items.items() if not item.active(now)]
            for key in expired:
                del self._items[key]
            return tuple(
                self._items[key]
                for key in sorted(self._items, key=lambda x: (x[0].value, x[1]))
            )
