"""Versioned immutable execution-plan storage."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from skeleton.shells.execution_plan import ExecutionPlan


@dataclass(frozen=True)
class StoredPlan:
    plan_id: str
    version: int
    fingerprint: str
    plan: ExecutionPlan
    created_at: float
    superseded: bool = False


class PlanConflict(RuntimeError):
    pass


class PlanStore:
    def __init__(
        self,
        *,
        max_versions: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_versions <= 0:
            raise ValueError("max_versions must be positive")
        self.max_versions = max_versions
        self._clock = clock
        self._versions: dict[str, list[StoredPlan]] = {}
        self._lock = threading.RLock()

    def put(
        self,
        plan: ExecutionPlan,
        *,
        expected_version: int | None = None,
    ) -> StoredPlan:
        with self._lock:
            versions = self._versions.setdefault(plan.plan_id, [])
            if sum(len(items) for items in self._versions.values()) >= self.max_versions:
                raise PlanConflict("plan store capacity exhausted")
            current_version = 0 if not versions else versions[-1].version
            if expected_version is not None and expected_version != current_version:
                raise PlanConflict("plan version conflict")
            if versions and versions[-1].fingerprint == plan.fingerprint:
                return versions[-1]

            if versions:
                last = versions[-1]
                versions[-1] = StoredPlan(
                    last.plan_id,
                    last.version,
                    last.fingerprint,
                    last.plan,
                    last.created_at,
                    superseded=True,
                )
            stored = StoredPlan(
                plan.plan_id,
                current_version + 1,
                plan.fingerprint,
                plan,
                self._clock(),
                superseded=False,
            )
            versions.append(stored)
            return stored

    def current(self, plan_id: str) -> StoredPlan:
        with self._lock:
            versions = self._versions[plan_id]
            return versions[-1]

    def at(self, plan_id: str, version: int) -> StoredPlan:
        if version <= 0:
            raise KeyError(version)
        with self._lock:
            versions = self._versions[plan_id]
            for item in versions:
                if item.version == version:
                    return item
        raise KeyError(version)

    def history(self, plan_id: str) -> tuple[StoredPlan, ...]:
        with self._lock:
            return tuple(self._versions.get(plan_id, ()))

    def remove(self, plan_id: str) -> bool:
        with self._lock:
            return self._versions.pop(plan_id, None) is not None

    def plan_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._versions))
