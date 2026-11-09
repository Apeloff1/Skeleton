"""Bounded low-cardinality metrics for shell workers."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class WorkerMetric:
    starts: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    duration_ms: float = 0.0
    output_bytes: int = 0
    recovered_claims: int = 0

    @property
    def attempts(self) -> int:
        return self.successes + self.failures

    @property
    def success_ratio(self) -> float:
        return 1.0 if self.attempts == 0 else self.successes / self.attempts

    @property
    def average_duration_ms(self) -> float:
        return 0.0 if self.attempts == 0 else self.duration_ms / self.attempts

    def to_dict(self) -> dict[str, int | float]:
        return {
            "starts": self.starts,
            "successes": self.successes,
            "failures": self.failures,
            "retries": self.retries,
            "duration_ms": self.duration_ms,
            "output_bytes": self.output_bytes,
            "recovered_claims": self.recovered_claims,
            "success_ratio": self.success_ratio,
            "average_duration_ms": self.average_duration_ms,
        }


@dataclass(frozen=True)
class WorkerMetricsSnapshot:
    workers: Mapping[str, WorkerMetric]

    def __post_init__(self) -> None:
        object.__setattr__(self, "workers", MappingProxyType(dict(self.workers)))

    @property
    def total_starts(self) -> int:
        return sum(metric.starts for metric in self.workers.values())

    @property
    def total_failures(self) -> int:
        return sum(metric.failures for metric in self.workers.values())

    @property
    def total_output_bytes(self) -> int:
        return sum(metric.output_bytes for metric in self.workers.values())

    def to_dict(self) -> dict[str, object]:
        return {
            "total_starts": self.total_starts,
            "total_failures": self.total_failures,
            "total_output_bytes": self.total_output_bytes,
            "workers": {key: value.to_dict() for key, value in self.workers.items()},
        }


class WorkerMetrics:
    """Thread-safe worker metric registry with bounded worker cardinality."""

    def __init__(self, *, max_workers: int = 4096) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self.max_workers = max_workers
        self._metrics: dict[str, WorkerMetric] = {}
        self._lock = threading.RLock()

    def _get(self, worker_id: str) -> WorkerMetric:
        metric = self._metrics.get(worker_id)
        if metric is None:
            if len(self._metrics) >= self.max_workers:
                raise RuntimeError("worker metric cardinality exhausted")
            metric = WorkerMetric()
            self._metrics[worker_id] = metric
        return metric

    def _replace(self, worker_id: str, **updates: int | float) -> WorkerMetric:
        current = self._get(worker_id)
        values = {
            "starts": current.starts,
            "successes": current.successes,
            "failures": current.failures,
            "retries": current.retries,
            "duration_ms": current.duration_ms,
            "output_bytes": current.output_bytes,
            "recovered_claims": current.recovered_claims,
        }
        values.update(updates)
        replacement = WorkerMetric(**values)
        self._metrics[worker_id] = replacement
        return replacement

    def started(self, worker_id: str) -> WorkerMetric:
        with self._lock:
            current = self._get(worker_id)
            return self._replace(worker_id, starts=current.starts + 1)

    def completed(
        self,
        worker_id: str,
        *,
        ok: bool,
        duration_ms: float,
        output_bytes: int,
    ) -> WorkerMetric:
        if duration_ms < 0 or output_bytes < 0:
            raise ValueError("metric values may not be negative")
        with self._lock:
            current = self._get(worker_id)
            return self._replace(
                worker_id,
                successes=current.successes + (1 if ok else 0),
                failures=current.failures + (0 if ok else 1),
                duration_ms=current.duration_ms + duration_ms,
                output_bytes=current.output_bytes + output_bytes,
            )

    def retried(self, worker_id: str, count: int = 1) -> WorkerMetric:
        if count <= 0:
            raise ValueError("retry count must be positive")
        with self._lock:
            current = self._get(worker_id)
            return self._replace(worker_id, retries=current.retries + count)

    def recovered(self, worker_id: str, claims: int = 1) -> WorkerMetric:
        if claims <= 0:
            raise ValueError("claims must be positive")
        with self._lock:
            current = self._get(worker_id)
            return self._replace(worker_id, recovered_claims=current.recovered_claims + claims)

    def get(self, worker_id: str) -> WorkerMetric:
        with self._lock:
            return self._metrics.get(worker_id, WorkerMetric())

    def snapshot(self) -> WorkerMetricsSnapshot:
        with self._lock:
            return WorkerMetricsSnapshot(dict(sorted(self._metrics.items())))

    def reset(self, worker_id: str | None = None) -> None:
        with self._lock:
            if worker_id is None:
                self._metrics.clear()
            else:
                self._metrics.pop(worker_id, None)
