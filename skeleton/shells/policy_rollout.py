"""Staged shell policy rollout with deterministic canary selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import threading
import time
from typing import Callable

from skeleton.shells.policy_store import PolicyRevision, PolicyStore
from skeleton.shells.runner import ShellPolicy


class RolloutPhase(str, Enum):
    PREPARED = "prepared"
    CANARY = "canary"
    BROAD = "broad"
    COMPLETE = "complete"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class PolicyRollout:
    rollout_id: str
    base_revision: int
    target_revision: int
    phase: RolloutPhase
    canary_percent: int
    created_at: float
    updated_at: float
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.rollout_id or len(self.rollout_id) > 128:
            raise ValueError("invalid rollout_id")
        if self.base_revision <= 0 or self.target_revision <= 0:
            raise ValueError("policy revisions must be positive")
        if not 0 <= self.canary_percent <= 100:
            raise ValueError("canary_percent must be between 0 and 100")


class PolicyRolloutManager:
    def __init__(
        self,
        store: PolicyStore,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self._clock = clock
        self._items: dict[str, PolicyRollout] = {}
        self._lock = threading.RLock()

    def prepare(
        self,
        rollout_id: str,
        policy: ShellPolicy,
        *,
        canary_percent: int = 5,
        reason: str = "",
    ) -> PolicyRollout:
        if rollout_id in self._items:
            raise RuntimeError("rollout_id already exists")
        base = self.store.current()
        target = self.store.compare_and_swap(base.revision, policy)
        now = self._clock()
        rollout = PolicyRollout(
            rollout_id,
            base.revision,
            target.revision,
            RolloutPhase.PREPARED,
            canary_percent,
            now,
            now,
            reason,
        )
        with self._lock:
            self._items[rollout_id] = rollout
        return rollout

    def _replace(self, current: PolicyRollout, phase: RolloutPhase) -> PolicyRollout:
        updated = PolicyRollout(
            current.rollout_id,
            current.base_revision,
            current.target_revision,
            phase,
            current.canary_percent,
            current.created_at,
            self._clock(),
            current.reason,
        )
        self._items[current.rollout_id] = updated
        return updated

    def advance(self, rollout_id: str) -> PolicyRollout:
        with self._lock:
            current = self._items[rollout_id]
            transitions = {
                RolloutPhase.PREPARED: RolloutPhase.CANARY,
                RolloutPhase.CANARY: RolloutPhase.BROAD,
                RolloutPhase.BROAD: RolloutPhase.COMPLETE,
            }
            target = transitions.get(current.phase)
            if target is None:
                raise RuntimeError("rollout cannot advance from current phase")
            return self._replace(current, target)

    def rollback(self, rollout_id: str) -> PolicyRollout:
        with self._lock:
            current = self._items[rollout_id]
            if current.phase in {RolloutPhase.COMPLETE, RolloutPhase.ROLLED_BACK}:
                raise RuntimeError("rollout cannot be rolled back from current phase")
            base = self.store.at(current.base_revision)
            self.store.replace(base.policy)
            return self._replace(current, RolloutPhase.ROLLED_BACK)

    def selected(self, rollout_id: str, principal: str) -> bool:
        with self._lock:
            rollout = self._items[rollout_id]
        if rollout.phase is RolloutPhase.PREPARED:
            return False
        if rollout.phase in {RolloutPhase.BROAD, RolloutPhase.COMPLETE}:
            return True
        if rollout.phase is RolloutPhase.ROLLED_BACK:
            return False
        bucket = int(hashlib.sha256(f"{rollout_id}:{principal}".encode()).hexdigest()[:8], 16) % 100
        return bucket < rollout.canary_percent

    def get(self, rollout_id: str) -> PolicyRollout:
        with self._lock:
            return self._items[rollout_id]

    def snapshot(self) -> tuple[PolicyRollout, ...]:
        with self._lock:
            return tuple(self._items[key] for key in sorted(self._items))
