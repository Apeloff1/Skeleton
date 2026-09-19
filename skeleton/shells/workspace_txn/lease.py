"""In-process CAS-style workspace leases with fencing generations."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable
import uuid


class WorkspaceLeaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceLease:
    lease_id: str
    workspace_id: str
    owner: str
    generation: int
    acquired_at: float
    expires_at: float

    @property
    def ttl_seconds(self) -> float:
        return max(0.0, self.expires_at - self.acquired_at)


class WorkspaceLeaseRegistry:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._active: dict[str, WorkspaceLease] = {}
        self._generation: dict[str, int] = {}
        self._lock = threading.RLock()

    def _purge_expired(self, workspace_id: str) -> None:
        current = self._active.get(workspace_id)
        if current is not None and current.expires_at <= self._clock():
            self._active.pop(workspace_id, None)

    def acquire(self, workspace_id: str, owner: str, *, ttl_seconds: float = 60.0) -> WorkspaceLease:
        if not workspace_id or not owner:
            raise ValueError("workspace_id and owner are required")
        if isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        with self._lock:
            self._purge_expired(workspace_id)
            if workspace_id in self._active:
                raise WorkspaceLeaseError("workspace is already leased")
            generation = self._generation.get(workspace_id, 0) + 1
            self._generation[workspace_id] = generation
            now = self._clock()
            lease = WorkspaceLease(
                uuid.uuid4().hex,
                workspace_id,
                owner,
                generation,
                now,
                now + float(ttl_seconds),
            )
            self._active[workspace_id] = lease
            return lease

    def renew(self, lease: WorkspaceLease, *, ttl_seconds: float = 60.0) -> WorkspaceLease:
        if isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        with self._lock:
            self._purge_expired(lease.workspace_id)
            current = self._active.get(lease.workspace_id)
            if current is None or current.lease_id != lease.lease_id or current.generation != lease.generation:
                raise WorkspaceLeaseError("lease is stale")
            now = self._clock()
            renewed = WorkspaceLease(
                current.lease_id,
                current.workspace_id,
                current.owner,
                current.generation,
                current.acquired_at,
                now + float(ttl_seconds),
            )
            self._active[current.workspace_id] = renewed
            return renewed

    def require(self, lease: WorkspaceLease) -> WorkspaceLease:
        with self._lock:
            self._purge_expired(lease.workspace_id)
            current = self._active.get(lease.workspace_id)
            if current is None:
                raise WorkspaceLeaseError("workspace lease is not active")
            if current.lease_id != lease.lease_id or current.generation != lease.generation:
                raise WorkspaceLeaseError("workspace lease fencing mismatch")
            return current

    def release(self, lease: WorkspaceLease) -> bool:
        with self._lock:
            current = self._active.get(lease.workspace_id)
            if current is None:
                return False
            if current.lease_id != lease.lease_id or current.generation != lease.generation:
                raise WorkspaceLeaseError("cannot release stale lease")
            self._active.pop(lease.workspace_id, None)
            return True

    def active(self, workspace_id: str) -> WorkspaceLease | None:
        with self._lock:
            self._purge_expired(workspace_id)
            return self._active.get(workspace_id)

    def snapshot(self) -> tuple[WorkspaceLease, ...]:
        with self._lock:
            for workspace_id in tuple(self._active):
                self._purge_expired(workspace_id)
            return tuple(sorted(self._active.values(), key=lambda lease: lease.workspace_id))
