"""Bounded outcome memory for AI shell planning.

Memory stores plan/evidence metadata only. Raw stdout, stderr, environment
values, and hidden model reasoning are intentionally excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class OutcomeMemory:
    memory_id: int
    intent_fingerprint: str
    proposal_fingerprint: str
    risk_score: int
    success: bool
    duration_ms: float
    verified: bool
    command_count: int
    observed_at: float
    model_id: str = ""

    def __post_init__(self) -> None:
        if self.memory_id <= 0:
            raise ValueError("memory_id must be positive")
        if len(self.intent_fingerprint) != 64 or len(self.proposal_fingerprint) != 64:
            raise ValueError("memory fingerprints must be SHA-256 hex")
        if not 0 <= self.risk_score <= 100:
            raise ValueError("risk_score out of range")
        if self.duration_ms < 0 or self.command_count <= 0:
            raise ValueError("invalid outcome memory metrics")

    def to_dict(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "intent_fingerprint": self.intent_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "risk_score": self.risk_score,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "verified": self.verified,
            "command_count": self.command_count,
            "observed_at": self.observed_at,
            "model_id": self.model_id,
        }


class AIOutcomeMemory:
    def __init__(
        self,
        *,
        max_items: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self._clock = clock
        self._serial = 0
        self._items: list[OutcomeMemory] = []
        self._lock = threading.RLock()

    def record(
        self,
        *,
        intent_fingerprint: str,
        proposal_fingerprint: str,
        risk_score: int,
        success: bool,
        duration_ms: float,
        verified: bool,
        command_count: int,
        model_id: str = "",
    ) -> OutcomeMemory:
        with self._lock:
            self._serial += 1
            item = OutcomeMemory(
                self._serial,
                intent_fingerprint,
                proposal_fingerprint,
                risk_score,
                bool(success),
                duration_ms,
                bool(verified),
                command_count,
                self._clock(),
                model_id,
            )
            self._items.append(item)
            if len(self._items) > self.max_items:
                self._items = self._items[-self.max_items :]
            return item

    def by_intent(self, intent_fingerprint: str) -> tuple[OutcomeMemory, ...]:
        with self._lock:
            return tuple(
                item for item in self._items
                if item.intent_fingerprint == intent_fingerprint
            )

    def by_model(self, model_id: str) -> tuple[OutcomeMemory, ...]:
        with self._lock:
            return tuple(item for item in self._items if item.model_id == model_id)

    def success_rate(self, *, model_id: str | None = None) -> float:
        with self._lock:
            items = self._items if model_id is None else [
                item for item in self._items if item.model_id == model_id
            ]
            if not items:
                return 0.5
            return sum(item.success for item in items) / len(items)

    def snapshot(self) -> tuple[OutcomeMemory, ...]:
        with self._lock:
            return tuple(self._items)
