"""Reusable resource budget primitives for shell sessions and pipelines."""

from __future__ import annotations

from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class ResourceLimits:
    max_commands: int = 100
    max_failures: int = 20
    max_duration_ms: float = 300_000.0
    max_stdout_bytes: int = 8 * 1024 * 1024
    max_stderr_bytes: int = 8 * 1024 * 1024
    max_retries: int = 20

    def __post_init__(self) -> None:
        values = (
            self.max_commands,
            self.max_failures,
            self.max_duration_ms,
            self.max_stdout_bytes,
            self.max_stderr_bytes,
            self.max_retries,
        )
        if any(value < 0 for value in values):
            raise ValueError("resource limits must be non-negative")

    def narrow(self, **overrides: int | float) -> "ResourceLimits":
        current = self.to_dict()
        for key, value in overrides.items():
            if key not in current:
                raise KeyError(key)
            if value > current[key]:
                raise ValueError(f"cannot widen resource limit {key}")
            current[key] = value
        return ResourceLimits(**current)

    def to_dict(self) -> dict[str, int | float]:
        return {
            "max_commands": self.max_commands,
            "max_failures": self.max_failures,
            "max_duration_ms": self.max_duration_ms,
            "max_stdout_bytes": self.max_stdout_bytes,
            "max_stderr_bytes": self.max_stderr_bytes,
            "max_retries": self.max_retries,
        }


@dataclass(frozen=True)
class ResourceUsage:
    commands: int = 0
    failures: int = 0
    duration_ms: float = 0.0
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    retries: int = 0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "commands": self.commands,
            "failures": self.failures,
            "duration_ms": self.duration_ms,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "retries": self.retries,
        }


class ResourceBudget:
    """Thread-safe resource counter with check-before-reserve semantics."""

    def __init__(self, limits: ResourceLimits) -> None:
        self.limits = limits
        self._usage = ResourceUsage()
        self._lock = threading.RLock()

    def snapshot(self) -> ResourceUsage:
        with self._lock:
            return self._usage

    def _replace(self, **changes: int | float) -> None:
        values = self._usage.to_dict()
        values.update(changes)
        self._usage = ResourceUsage(**values)

    def can_start(self) -> bool:
        with self._lock:
            return self._usage.commands < self.limits.max_commands

    def reserve_command(self) -> bool:
        with self._lock:
            if self._usage.commands >= self.limits.max_commands:
                return False
            self._replace(commands=self._usage.commands + 1)
            return True

    def record_retry(self) -> bool:
        with self._lock:
            if self._usage.retries >= self.limits.max_retries:
                return False
            self._replace(retries=self._usage.retries + 1)
            return True

    def record_result(
        self,
        *,
        ok: bool,
        duration_ms: float,
        stdout_bytes: int,
        stderr_bytes: int,
    ) -> None:
        with self._lock:
            self._replace(
                failures=self._usage.failures + (0 if ok else 1),
                duration_ms=self._usage.duration_ms + max(0.0, duration_ms),
                stdout_bytes=self._usage.stdout_bytes + max(0, stdout_bytes),
                stderr_bytes=self._usage.stderr_bytes + max(0, stderr_bytes),
            )

    def exceeded(self) -> tuple[str, ...]:
        with self._lock:
            usage = self._usage
            limits = self.limits
            reasons: list[str] = []
            if usage.commands > limits.max_commands:
                reasons.append("commands")
            if usage.failures > limits.max_failures:
                reasons.append("failures")
            if usage.duration_ms > limits.max_duration_ms:
                reasons.append("duration_ms")
            if usage.stdout_bytes > limits.max_stdout_bytes:
                reasons.append("stdout_bytes")
            if usage.stderr_bytes > limits.max_stderr_bytes:
                reasons.append("stderr_bytes")
            if usage.retries > limits.max_retries:
                reasons.append("retries")
            return tuple(reasons)

    def healthy(self) -> bool:
        return not self.exceeded()
