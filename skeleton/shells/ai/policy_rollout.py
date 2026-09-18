"""Staged rollout for AI autonomy policy revisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import threading
import time
from typing import Callable

from skeleton.shells.ai.policy import AIShellPolicy
from skeleton.shells.ai.policy_store import AIPolicyRevision, AIPolicyStore


class AIPolicyRolloutPhase(str, Enum):
    PREPARED = "prepared"
    CANARY = "canary"
    BROAD = "broad"
    COMPLETE = "complete"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class AIPolicyRollout:
    rollout_id: str
    base_revision: int
    target_revision: int
    phase: AIPolicyRolloutPhase
    canary_percent: int
    created_at: float
    updated_at: float
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "rollout_id": self.rollout_id,
            "base_revision": self.base_revision,
            "target_revision": self.target_revision,
            "phase": self.phase.value,
            "canary_percent": self.canary_percent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reason": self.reason,
        }


class AIPolicyRolloutManager:
    def __init__(
        self,
        store: AIPolicyStore,
        *,
        max_rollouts: int = 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.max_rollouts = max_rollouts
        self._clock = clock
        self._items: dict[str, AIPolicyRollout] = {}
        self._base: dict[str, AIShellPolicy] = {}
        self._lock = threading.RLock()

    def prepare(
        self,
        rollout_id: str,
        target: AIShellPolicy,
        *,
        canary_percent: int = 10,
        reason: str = "",
    ) -> AIPolicyRollout:
        if not rollout_id or len(rollout_id) > 160:
            raise ValueError("invalid rollout_id")
        if not 0 <= canary_percent <= 100:
            raise ValueError("canary_percent out of range")
        with self._lock:
            if rollout_id in self._items:
                raise ValueError("rollout already exists")
            if len(self._items) >= self.max_rollouts:
                raise RuntimeError("AI policy rollout capacity exhausted")
            base = self.store.current()
            target_revision = self.store.compare_and_swap(base.revision, target)
            now = self._clock()
            item = AIPolicyRollout(
                rollout_id,
                base.revision,
                target_revision.revision,
                AIPolicyRolloutPhase.PREPARED,
                canary_percent,
                now,
                now,
                reason,
            )
            self._items[rollout_id] = item
            self._base[rollout_id] = base.policy
            return item

    def _replace(self, item: AIPolicyRollout, phase: AIPolicyRolloutPhase) -> AIPolicyRollout:
        updated = AIPolicyRollout(
            item.rollout_id,
            item.base_revision,
            item.target_revision,
            phase,
            item.canary_percent,
            item.created_at,
            self._clock(),
            item.reason,
        )
        self._items[item.rollout_id] = updated
        return updated

    def advance(self, rollout_id: str) -> AIPolicyRollout:
        with self._lock:
            item = self._items[rollout_id]
            next_phase = {
                AIPolicyRolloutPhase.PREPARED: AIPolicyRolloutPhase.CANARY,
                AIPolicyRolloutPhase.CANARY: AIPolicyRolloutPhase.BROAD,
                AIPolicyRolloutPhase.BROAD: AIPolicyRolloutPhase.COMPLETE,
            }.get(item.phase)
            if next_phase is None:
                raise RuntimeError("AI policy rollout cannot advance")
            return self._replace(item, next_phase)

    def selected(self, rollout_id: str, principal: str) -> bool:
        with self._lock:
            item = self._items[rollout_id]
            if item.phase is AIPolicyRolloutPhase.PREPARED:
                return False
            if item.phase in {AIPolicyRolloutPhase.BROAD, AIPolicyRolloutPhase.COMPLETE}:
                return True
            if item.phase is AIPolicyRolloutPhase.ROLLED_BACK:
                return False
            raw = hashlib.sha256(f"{rollout_id}:{principal}".encode()).digest()
            bucket = int.from_bytes(raw[:4], "big") % 100
            return bucket < item.canary_percent

    def rollback(self, rollout_id: str) -> AIPolicyRollout:
        with self._lock:
            item = self._items[rollout_id]
            if item.phase is AIPolicyRolloutPhase.COMPLETE:
                raise RuntimeError("completed AI policy rollout cannot be rolled back implicitly")
            if item.phase is AIPolicyRolloutPhase.ROLLED_BACK:
                return item
            self.store.replace(self._base[rollout_id])
            return self._replace(item, AIPolicyRolloutPhase.ROLLED_BACK)

    def get(self, rollout_id: str) -> AIPolicyRollout:
        with self._lock:
            return self._items[rollout_id]
