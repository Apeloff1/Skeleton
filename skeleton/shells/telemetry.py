"""In-process shell execution telemetry without high-cardinality labels."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class CommandMetrics:
    started: int = 0
    completed: int = 0
    failed: int = 0
    timed_out: int = 0
    output_limited: int = 0
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    duration_ms_total: float = 0.0
    retries: int = 0

    @property
    def average_duration_ms(self) -> float:
        return self.duration_ms_total / self.completed if self.completed else 0.0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "started": self.started,
            "completed": self.completed,
            "failed": self.failed,
            "timed_out": self.timed_out,
            "output_limited": self.output_limited,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "duration_ms_total": self.duration_ms_total,
            "average_duration_ms": self.average_duration_ms,
            "retries": self.retries,
        }


class ShellTelemetry:
    """Thread-safe bounded metric registry keyed only by registered command name."""

    def __init__(self, *, max_commands: int = 256) -> None:
        if max_commands <= 0:
            raise ValueError("max_commands must be positive")
        self.max_commands = max_commands
        self._metrics: dict[str, dict[str, int | float]] = {}
        self._lock = threading.RLock()

    def _bucket(self, command: str) -> dict[str, int | float]:
        bucket = self._metrics.get(command)
        if bucket is None:
            if len(self._metrics) >= self.max_commands:
                command = "[overflow]"
                bucket = self._metrics.get(command)
            if bucket is None:
                bucket = {
                    "started": 0,
                    "completed": 0,
                    "failed": 0,
                    "timed_out": 0,
                    "output_limited": 0,
                    "stdout_bytes": 0,
                    "stderr_bytes": 0,
                    "duration_ms_total": 0.0,
                    "retries": 0,
                }
                self._metrics[command] = bucket
        return bucket

    def started(self, command: str) -> None:
        with self._lock:
            bucket = self._bucket(command)
            bucket["started"] = int(bucket["started"]) + 1

    def retried(self, command: str) -> None:
        with self._lock:
            bucket = self._bucket(command)
            bucket["retries"] = int(bucket["retries"]) + 1

    def completed(
        self,
        command: str,
        *,
        ok: bool,
        timed_out: bool,
        output_limited: bool,
        stdout_bytes: int,
        stderr_bytes: int,
        duration_ms: float,
    ) -> None:
        with self._lock:
            bucket = self._bucket(command)
            bucket["completed"] = int(bucket["completed"]) + 1
            if not ok:
                bucket["failed"] = int(bucket["failed"]) + 1
            if timed_out:
                bucket["timed_out"] = int(bucket["timed_out"]) + 1
            if output_limited:
                bucket["output_limited"] = int(bucket["output_limited"]) + 1
            bucket["stdout_bytes"] = int(bucket["stdout_bytes"]) + max(0, stdout_bytes)
            bucket["stderr_bytes"] = int(bucket["stderr_bytes"]) + max(0, stderr_bytes)
            bucket["duration_ms_total"] = float(bucket["duration_ms_total"]) + max(0.0, duration_ms)

    def snapshot(self) -> Mapping[str, CommandMetrics]:
        with self._lock:
            result = {
                command: CommandMetrics(
                    started=int(bucket["started"]),
                    completed=int(bucket["completed"]),
                    failed=int(bucket["failed"]),
                    timed_out=int(bucket["timed_out"]),
                    output_limited=int(bucket["output_limited"]),
                    stdout_bytes=int(bucket["stdout_bytes"]),
                    stderr_bytes=int(bucket["stderr_bytes"]),
                    duration_ms_total=float(bucket["duration_ms_total"]),
                    retries=int(bucket["retries"]),
                )
                for command, bucket in self._metrics.items()
            }
        return MappingProxyType(result)

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()
