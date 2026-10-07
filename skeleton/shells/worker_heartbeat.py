"""Heartbeat and liveness tracking for registered shell workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping

from skeleton.shells.worker_identity import WorkerIdentity, WorkerIdentityError, WorkerRegistry


class WorkerLiveness(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    LATE = "late"
    STALE = "stale"


class HeartbeatError(ValueError):
    pass


@dataclass(frozen=True)
class HeartbeatPolicy:
    late_after_seconds: float = 10.0
    stale_after_seconds: float = 30.0
    max_sequence_gap: int = 1_000_000
    max_metrics: int = 64

    def __post_init__(self) -> None:
        if self.late_after_seconds <= 0:
            raise HeartbeatError("late_after_seconds must be positive")
        if self.stale_after_seconds <= self.late_after_seconds:
            raise HeartbeatError("stale_after_seconds must exceed late_after_seconds")
        if self.max_sequence_gap <= 0:
            raise HeartbeatError("max_sequence_gap must be positive")
        if self.max_metrics <= 0 or self.max_metrics > 1024:
            raise HeartbeatError("max_metrics outside supported bounds")


def _freeze_metrics(metrics: Mapping[str, float], policy: HeartbeatPolicy) -> Mapping[str, float]:
    if len(metrics) > policy.max_metrics:
        raise HeartbeatError("too many heartbeat metrics")
    clean: dict[str, float] = {}
    for key, value in metrics.items():
        if not isinstance(key, str) or not key or len(key) > 128:
            raise HeartbeatError("invalid heartbeat metric key")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HeartbeatError("heartbeat metric values must be numeric")
        numeric = float(value)
        if numeric != numeric or numeric in (float("inf"), float("-inf")):
            raise HeartbeatError("heartbeat metrics must be finite")
        clean[key] = numeric
    return MappingProxyType(clean)


@dataclass(frozen=True)
class WorkerHeartbeat:
    identity: WorkerIdentity
    sequence: int
    observed_at: float
    metrics: Mapping[str, float] = field(default_factory=dict)
    busy: bool = False
    inflight: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise HeartbeatError("heartbeat sequence must be positive")
        if self.observed_at < 0:
            raise HeartbeatError("observed_at may not be negative")
        if isinstance(self.inflight, bool) or not isinstance(self.inflight, int) or self.inflight < 0:
            raise HeartbeatError("inflight must be a non-negative integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_dict(),
            "sequence": self.sequence,
            "observed_at": self.observed_at,
            "metrics": dict(self.metrics),
            "busy": self.busy,
            "inflight": self.inflight,
        }


@dataclass(frozen=True)
class LivenessView:
    worker_id: str
    generation: int
    liveness: WorkerLiveness
    age_seconds: float | None
    sequence: int | None
    busy: bool
    inflight: int

    def to_dict(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "generation": self.generation,
            "liveness": self.liveness.value,
            "age_seconds": self.age_seconds,
            "sequence": self.sequence,
            "busy": self.busy,
            "inflight": self.inflight,
        }


@dataclass(frozen=True)
class HeartbeatSnapshot:
    views: tuple[LivenessView, ...]
    created_at: float

    def count(self, state: WorkerLiveness) -> int:
        return sum(view.liveness is state for view in self.views)

    @property
    def healthy(self) -> int:
        return self.count(WorkerLiveness.HEALTHY)

    @property
    def late(self) -> int:
        return self.count(WorkerLiveness.LATE)

    @property
    def stale(self) -> int:
        return self.count(WorkerLiveness.STALE)

    def to_dict(self) -> dict[str, object]:
        return {
            "created_at": self.created_at,
            "healthy": self.healthy,
            "late": self.late,
            "stale": self.stale,
            "views": [view.to_dict() for view in self.views],
        }


class HeartbeatRegistry:
    """Generation-aware worker heartbeat table."""

    def __init__(
        self,
        *,
        workers: WorkerRegistry | None = None,
        policy: HeartbeatPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_workers: int = 4096,
    ) -> None:
        self.workers = workers
        self.policy = policy or HeartbeatPolicy()
        self._clock = clock
        self.max_workers = max_workers
        self._heartbeats: dict[str, WorkerHeartbeat] = {}
        self._lock = threading.RLock()

    def beat(
        self,
        identity: WorkerIdentity,
        *,
        sequence: int,
        metrics: Mapping[str, float] | None = None,
        busy: bool = False,
        inflight: int = 0,
    ) -> WorkerHeartbeat:
        if self.workers is not None:
            self.workers.require_current(identity)
        now = self._clock()
        clean_metrics = _freeze_metrics(metrics or {}, self.policy)
        heartbeat = WorkerHeartbeat(
            identity=identity,
            sequence=sequence,
            observed_at=now,
            metrics=clean_metrics,
            busy=bool(busy),
            inflight=inflight,
        )
        with self._lock:
            previous = self._heartbeats.get(identity.worker_id)
            if previous is None:
                if len(self._heartbeats) >= self.max_workers:
                    raise HeartbeatError("heartbeat registry capacity exhausted")
            else:
                if identity.generation < previous.identity.generation:
                    raise HeartbeatError("heartbeat generation is stale")
                if identity.generation == previous.identity.generation:
                    if sequence <= previous.sequence:
                        raise HeartbeatError("heartbeat sequence must increase")
                    if sequence - previous.sequence > self.policy.max_sequence_gap:
                        raise HeartbeatError("heartbeat sequence gap exceeds policy")
            self._heartbeats[identity.worker_id] = heartbeat
            return heartbeat

    def latest(self, worker_id: str) -> WorkerHeartbeat | None:
        with self._lock:
            return self._heartbeats.get(worker_id)

    def liveness(self, identity: WorkerIdentity) -> LivenessView:
        with self._lock:
            heartbeat = self._heartbeats.get(identity.worker_id)
            if heartbeat is None or heartbeat.identity.generation != identity.generation:
                return LivenessView(
                    identity.worker_id,
                    identity.generation,
                    WorkerLiveness.UNKNOWN,
                    None,
                    None,
                    False,
                    0,
                )
            age = max(0.0, self._clock() - heartbeat.observed_at)
            if age >= self.policy.stale_after_seconds:
                state = WorkerLiveness.STALE
            elif age >= self.policy.late_after_seconds:
                state = WorkerLiveness.LATE
            else:
                state = WorkerLiveness.HEALTHY
            return LivenessView(
                identity.worker_id,
                identity.generation,
                state,
                age,
                heartbeat.sequence,
                heartbeat.busy,
                heartbeat.inflight,
            )

    def forget(self, identity: WorkerIdentity) -> bool:
        with self._lock:
            current = self._heartbeats.get(identity.worker_id)
            if current is None or current.identity.generation != identity.generation:
                return False
            del self._heartbeats[identity.worker_id]
            return True

    def stale(self) -> tuple[WorkerHeartbeat, ...]:
        now = self._clock()
        with self._lock:
            result = [
                heartbeat
                for heartbeat in self._heartbeats.values()
                if now - heartbeat.observed_at >= self.policy.stale_after_seconds
            ]
            return tuple(sorted(result, key=lambda item: item.identity.key))

    def prune_stale(self) -> tuple[WorkerHeartbeat, ...]:
        with self._lock:
            stale = self.stale()
            for heartbeat in stale:
                current = self._heartbeats.get(heartbeat.identity.worker_id)
                if current is heartbeat:
                    del self._heartbeats[heartbeat.identity.worker_id]
            return stale

    def snapshot(self) -> HeartbeatSnapshot:
        now = self._clock()
        with self._lock:
            views: list[LivenessView] = []
            for heartbeat in sorted(self._heartbeats.values(), key=lambda item: item.identity.key):
                age = max(0.0, now - heartbeat.observed_at)
                if age >= self.policy.stale_after_seconds:
                    state = WorkerLiveness.STALE
                elif age >= self.policy.late_after_seconds:
                    state = WorkerLiveness.LATE
                else:
                    state = WorkerLiveness.HEALTHY
                views.append(
                    LivenessView(
                        heartbeat.identity.worker_id,
                        heartbeat.identity.generation,
                        state,
                        age,
                        heartbeat.sequence,
                        heartbeat.busy,
                        heartbeat.inflight,
                    )
                )
            return HeartbeatSnapshot(tuple(views), now)
