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


class WorkspaceLeaseHeartbeat:
    """Keep an in-process workspace lease alive across long blocking work.

    The lease id and fencing generation remain stable across renewals, so the
    original WorkspaceLease token remains a valid capability while the registry
    advances only its expiration timestamp.
    """

    def __init__(
        self,
        registry: WorkspaceLeaseRegistry,
        lease: WorkspaceLease,
        *,
        ttl_seconds: float,
        interval_seconds: float | None = None,
    ) -> None:
        if isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise ValueError("heartbeat ttl must be positive")
        if isinstance(interval_seconds, bool):
            raise ValueError("heartbeat interval must be numeric")
        interval = (
            min(float(ttl_seconds) / 3.0, 30.0)
            if interval_seconds is None
            else float(interval_seconds)
        )
        if interval <= 0 or interval >= float(ttl_seconds):
            raise ValueError("heartbeat interval must be positive and below ttl")
        self.registry = registry
        self.lease = lease
        self.ttl_seconds = float(ttl_seconds)
        self.interval_seconds = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    @property
    def error(self) -> Exception | None:
        with self._lock:
            return self._error

    def _record_error(self, exc: Exception) -> None:
        with self._lock:
            if self._error is None:
                self._error = exc

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.registry.renew(
                    self.lease,
                    ttl_seconds=self.ttl_seconds,
                )
            except Exception as exc:
                self._record_error(exc)
                self._stop.set()
                return

    def start(self) -> "WorkspaceLeaseHeartbeat":
        if self._thread is not None:
            raise WorkspaceLeaseError("lease heartbeat has already been started")
        thread = threading.Thread(
            target=self._run,
            name=f"workspace-lease-{self.lease.workspace_id[:12]}",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return self

    def require_healthy(self) -> WorkspaceLease:
        error = self.error
        if error is not None:
            raise WorkspaceLeaseError("workspace lease heartbeat failed") from error
        return self.registry.require(self.lease)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, min(self.interval_seconds * 2.0, 5.0)))

    def __enter__(self) -> "WorkspaceLeaseHeartbeat":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
