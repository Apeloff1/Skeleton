"""Worker lifecycle supervision, fault budgets, and quarantine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable

from skeleton.shells.worker_identity import WorkerIdentity, WorkerRegistry


class SupervisionState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    QUARANTINED = "quarantined"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass(frozen=True)
class SupervisorPolicy:
    max_faults: int = 5
    fault_window_seconds: float = 60.0
    quarantine_seconds: float = 120.0
    max_restarts: int = 10
    restart_window_seconds: float = 3600.0

    def __post_init__(self) -> None:
        if self.max_faults <= 0 or self.max_restarts <= 0:
            raise ValueError("fault/restart limits must be positive")
        if self.fault_window_seconds <= 0 or self.quarantine_seconds <= 0 or self.restart_window_seconds <= 0:
            raise ValueError("supervisor time windows must be positive")


@dataclass(frozen=True)
class WorkerFault:
    observed_at: float
    kind: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.observed_at < 0:
            raise ValueError("fault timestamp may not be negative")
        if not self.kind or len(self.kind) > 128:
            raise ValueError("invalid fault kind")
        if len(self.detail) > 512:
            raise ValueError("fault detail too long")


@dataclass(frozen=True)
class SupervisedWorker:
    identity: WorkerIdentity
    state: SupervisionState
    faults: tuple[WorkerFault, ...] = ()
    restarts: tuple[float, ...] = ()
    quarantine_until: float = 0.0
    updated_at: float = 0.0

    @property
    def quarantined(self) -> bool:
        return self.state is SupervisionState.QUARANTINED

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_dict(),
            "state": self.state.value,
            "faults": [
                {"observed_at": fault.observed_at, "kind": fault.kind, "detail": fault.detail}
                for fault in self.faults
            ],
            "restarts": list(self.restarts),
            "quarantine_until": self.quarantine_until,
            "updated_at": self.updated_at,
        }


class WorkerSupervisor:
    """Generation-aware lifecycle state machine."""

    def __init__(
        self,
        workers: WorkerRegistry,
        *,
        policy: SupervisorPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.workers = workers
        self.policy = policy or SupervisorPolicy()
        self._clock = clock
        self._states: dict[str, SupervisedWorker] = {}
        self._lock = threading.RLock()

    def attach(self, identity: WorkerIdentity) -> SupervisedWorker:
        self.workers.require_current(identity)
        with self._lock:
            existing = self._states.get(identity.worker_id)
            if existing is not None and existing.identity.generation >= identity.generation:
                if existing.identity.generation == identity.generation:
                    return existing
                raise RuntimeError("cannot attach stale worker generation")
            now = self._clock()
            state = SupervisedWorker(identity, SupervisionState.STARTING, updated_at=now)
            self._states[identity.worker_id] = state
            return state

    def _replace(
        self,
        current: SupervisedWorker,
        *,
        state: SupervisionState | None = None,
        faults: tuple[WorkerFault, ...] | None = None,
        restarts: tuple[float, ...] | None = None,
        quarantine_until: float | None = None,
    ) -> SupervisedWorker:
        updated = SupervisedWorker(
            identity=current.identity,
            state=current.state if state is None else state,
            faults=current.faults if faults is None else faults,
            restarts=current.restarts if restarts is None else restarts,
            quarantine_until=current.quarantine_until if quarantine_until is None else quarantine_until,
            updated_at=self._clock(),
        )
        self._states[current.identity.worker_id] = updated
        return updated

    def mark_running(self, identity: WorkerIdentity) -> SupervisedWorker:
        with self._lock:
            current = self.require(identity)
            if current.state not in {SupervisionState.STARTING, SupervisionState.DEGRADED}:
                raise RuntimeError("worker cannot enter running from current state")
            return self._replace(current, state=SupervisionState.RUNNING)

    def fault(self, identity: WorkerIdentity, kind: str, detail: str = "") -> SupervisedWorker:
        now = self._clock()
        with self._lock:
            current = self.require(identity)
            threshold = now - self.policy.fault_window_seconds
            faults = tuple(fault for fault in current.faults if fault.observed_at >= threshold)
            faults = faults + (WorkerFault(now, kind, detail),)
            if len(faults) >= self.policy.max_faults:
                self.workers.set_enabled(identity, False)
                return self._replace(
                    current,
                    state=SupervisionState.QUARANTINED,
                    faults=faults,
                    quarantine_until=now + self.policy.quarantine_seconds,
                )
            return self._replace(current, state=SupervisionState.DEGRADED, faults=faults)

    def restart(self, identity: WorkerIdentity) -> SupervisedWorker:
        now = self._clock()
        with self._lock:
            current = self.require(identity)
            threshold = now - self.policy.restart_window_seconds
            restarts = tuple(value for value in current.restarts if value >= threshold)
            if len(restarts) >= self.policy.max_restarts:
                self.workers.set_enabled(identity, False)
                return self._replace(
                    current,
                    state=SupervisionState.QUARANTINED,
                    restarts=restarts,
                    quarantine_until=now + self.policy.quarantine_seconds,
                )
            restarts = restarts + (now,)
            return self._replace(current, state=SupervisionState.STARTING, restarts=restarts)

    def begin_stop(self, identity: WorkerIdentity) -> SupervisedWorker:
        with self._lock:
            current = self.require(identity)
            if current.state is SupervisionState.STOPPED:
                return current
            return self._replace(current, state=SupervisionState.STOPPING)

    def stopped(self, identity: WorkerIdentity) -> SupervisedWorker:
        with self._lock:
            current = self.require(identity)
            if current.state not in {SupervisionState.STOPPING, SupervisionState.QUARANTINED}:
                raise RuntimeError("worker must be stopping or quarantined before stopped")
            return self._replace(current, state=SupervisionState.STOPPED)

    def release_quarantine(self, identity: WorkerIdentity) -> SupervisedWorker:
        now = self._clock()
        with self._lock:
            current = self.require(identity)
            if current.state is not SupervisionState.QUARANTINED:
                raise RuntimeError("worker is not quarantined")
            if now < current.quarantine_until:
                raise RuntimeError("quarantine has not expired")
            self.workers.set_enabled(identity, True)
            return self._replace(
                current,
                state=SupervisionState.STARTING,
                faults=(),
                quarantine_until=0.0,
            )

    def require(self, identity: WorkerIdentity) -> SupervisedWorker:
        current = self._states.get(identity.worker_id)
        if current is None:
            raise KeyError(identity.worker_id)
        if current.identity.generation != identity.generation:
            raise RuntimeError("supervisor generation is stale")
        return current

    def get(self, worker_id: str) -> SupervisedWorker | None:
        with self._lock:
            return self._states.get(worker_id)

    def snapshot(self) -> tuple[SupervisedWorker, ...]:
        with self._lock:
            return tuple(sorted(self._states.values(), key=lambda item: item.identity.key))
