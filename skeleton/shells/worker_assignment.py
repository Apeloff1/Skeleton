"""Generation-safe worker assignment tokens."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Callable

from skeleton.shells.worker_identity import WorkerIdentity, WorkerRegistry


@dataclass(frozen=True)
class WorkerAssignment:
    assignment_id: str
    item_id: str
    worker: WorkerIdentity
    created_at: float
    expires_at: float
    revision: int = 1

    @property
    def expired(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "assignment_id": self.assignment_id,
            "item_id": self.item_id,
            "worker": self.worker.to_dict(),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revision": self.revision,
        }


class AssignmentConflict(RuntimeError):
    pass


class WorkerAssignments:
    """Bounded assignment registry protected by worker generations."""

    def __init__(
        self,
        workers: WorkerRegistry,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_assignments: int = 10000,
    ) -> None:
        self.workers = workers
        self._clock = clock
        self.max_assignments = max_assignments
        self._items: dict[str, WorkerAssignment] = {}
        self._lock = threading.RLock()
        self._serial = 0

    def _prune(self) -> None:
        now = self._clock()
        expired = [key for key, value in self._items.items() if value.expires_at <= now]
        for key in expired:
            del self._items[key]

    def assign(
        self,
        item_id: str,
        worker: WorkerIdentity,
        *,
        ttl_seconds: float = 60.0,
    ) -> WorkerAssignment:
        if not item_id or len(item_id) > 256:
            raise ValueError("invalid item_id")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.workers.require_current(worker)
        with self._lock:
            self._prune()
            if item_id in self._items:
                raise AssignmentConflict("item already assigned")
            if len(self._items) >= self.max_assignments:
                raise AssignmentConflict("assignment capacity exhausted")
            self._serial += 1
            now = self._clock()
            token = hashlib.sha256(
                f"{item_id}:{worker.key}:{self._serial}:{now}".encode("utf-8")
            ).hexdigest()[:32]
            assignment = WorkerAssignment(
                assignment_id=token,
                item_id=item_id,
                worker=worker,
                created_at=now,
                expires_at=now + ttl_seconds,
            )
            self._items[item_id] = assignment
            return assignment

    def renew(self, assignment: WorkerAssignment, *, ttl_seconds: float = 60.0) -> WorkerAssignment:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.workers.require_current(assignment.worker)
        with self._lock:
            self._prune()
            current = self._items.get(assignment.item_id)
            if current != assignment:
                raise AssignmentConflict("assignment is stale")
            now = self._clock()
            renewed = WorkerAssignment(
                assignment_id=current.assignment_id,
                item_id=current.item_id,
                worker=current.worker,
                created_at=current.created_at,
                expires_at=now + ttl_seconds,
                revision=current.revision + 1,
            )
            self._items[current.item_id] = renewed
            return renewed

    def release(self, assignment: WorkerAssignment) -> bool:
        with self._lock:
            current = self._items.get(assignment.item_id)
            if current != assignment:
                return False
            del self._items[assignment.item_id]
            return True

    def require(self, assignment: WorkerAssignment) -> WorkerAssignment:
        self.workers.require_current(assignment.worker)
        with self._lock:
            self._prune()
            current = self._items.get(assignment.item_id)
            if current != assignment:
                raise AssignmentConflict("assignment is stale or expired")
            return current

    def by_worker(self, worker: WorkerIdentity) -> tuple[WorkerAssignment, ...]:
        with self._lock:
            self._prune()
            return tuple(
                sorted(
                    (item for item in self._items.values() if item.worker == worker),
                    key=lambda item: item.item_id,
                )
            )

    def snapshot(self) -> tuple[WorkerAssignment, ...]:
        with self._lock:
            self._prune()
            return tuple(sorted(self._items.values(), key=lambda item: item.item_id))
