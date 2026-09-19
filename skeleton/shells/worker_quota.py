"""Per-principal worker admission quotas with explicit reservations."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class WorkerQuota:
    max_inflight: int = 8
    max_starts_per_window: int = 100
    window_seconds: float = 60.0
    max_failures_per_window: int = 25
    max_output_bytes_per_window: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        integers = (
            self.max_inflight,
            self.max_starts_per_window,
            self.max_failures_per_window,
            self.max_output_bytes_per_window,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in integers):
            raise ValueError("worker quota integer values must be non-negative")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")


@dataclass(frozen=True)
class QuotaUsage:
    window_started_at: float
    starts: int = 0
    inflight: int = 0
    failures: int = 0
    output_bytes: int = 0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "window_started_at": self.window_started_at,
            "starts": self.starts,
            "inflight": self.inflight,
            "failures": self.failures,
            "output_bytes": self.output_bytes,
        }


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    retry_after_seconds: float
    principal: str
    usage: QuotaUsage

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "retry_after_seconds": self.retry_after_seconds,
            "principal": self.principal,
            "usage": self.usage.to_dict(),
        }


@dataclass(frozen=True)
class QuotaReservation:
    reservation_id: int
    principal: str
    window_started_at: float
    started_at: float


class WorkerQuotaLedger:
    """Thread-safe fixed-window quota ledger."""

    def __init__(
        self,
        quota: WorkerQuota | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_principals: int = 4096,
    ) -> None:
        self.quota = quota or WorkerQuota()
        self._clock = clock
        self.max_principals = max_principals
        self._usage: dict[str, QuotaUsage] = {}
        self._reservations: dict[int, QuotaReservation] = {}
        self._serial = 0
        self._lock = threading.RLock()

    def _validate_principal(self, principal: str) -> str:
        if not isinstance(principal, str) or not principal.strip() or len(principal) > 256:
            raise ValueError("invalid quota principal")
        return principal

    def _current_usage(self, principal: str, now: float) -> QuotaUsage:
        usage = self._usage.get(principal)
        if usage is None:
            if len(self._usage) >= self.max_principals:
                raise RuntimeError("quota principal capacity exhausted")
            usage = QuotaUsage(window_started_at=now)
            self._usage[principal] = usage
            return usage
        if now - usage.window_started_at >= self.quota.window_seconds:
            usage = QuotaUsage(window_started_at=now, inflight=usage.inflight)
            self._usage[principal] = usage
        return usage

    def inspect(self, principal: str) -> QuotaDecision:
        principal = self._validate_principal(principal)
        with self._lock:
            now = self._clock()
            usage = self._current_usage(principal, now)
            retry = max(0.0, self.quota.window_seconds - (now - usage.window_started_at))
            if usage.inflight >= self.quota.max_inflight:
                return QuotaDecision(False, "inflight quota exhausted", 0.0, principal, usage)
            if usage.starts >= self.quota.max_starts_per_window:
                return QuotaDecision(False, "start quota exhausted", retry, principal, usage)
            if usage.failures >= self.quota.max_failures_per_window:
                return QuotaDecision(False, "failure quota exhausted", retry, principal, usage)
            if usage.output_bytes >= self.quota.max_output_bytes_per_window:
                return QuotaDecision(False, "output quota exhausted", retry, principal, usage)
            return QuotaDecision(True, "allowed", 0.0, principal, usage)

    def reserve(self, principal: str) -> QuotaReservation:
        with self._lock:
            decision = self.inspect(principal)
            if not decision.allowed:
                raise RuntimeError(decision.reason)
            now = self._clock()
            usage = self._current_usage(principal, now)
            updated = QuotaUsage(
                window_started_at=usage.window_started_at,
                starts=usage.starts + 1,
                inflight=usage.inflight + 1,
                failures=usage.failures,
                output_bytes=usage.output_bytes,
            )
            self._usage[principal] = updated
            self._serial += 1
            reservation = QuotaReservation(
                self._serial,
                principal,
                updated.window_started_at,
                now,
            )
            self._reservations[reservation.reservation_id] = reservation
            return reservation

    def complete(
        self,
        reservation: QuotaReservation,
        *,
        ok: bool,
        output_bytes: int = 0,
    ) -> QuotaUsage:
        if isinstance(output_bytes, bool) or not isinstance(output_bytes, int) or output_bytes < 0:
            raise ValueError("output_bytes must be a non-negative integer")
        with self._lock:
            current = self._reservations.pop(reservation.reservation_id, None)
            if current != reservation:
                raise RuntimeError("quota reservation is stale or already completed")
            now = self._clock()
            usage = self._current_usage(reservation.principal, now)
            updated = QuotaUsage(
                window_started_at=usage.window_started_at,
                starts=usage.starts,
                inflight=max(0, usage.inflight - 1),
                failures=usage.failures + (0 if ok else 1),
                output_bytes=usage.output_bytes + output_bytes,
            )
            self._usage[reservation.principal] = updated
            return updated

    def release(self, reservation: QuotaReservation) -> QuotaUsage:
        with self._lock:
            current = self._reservations.pop(reservation.reservation_id, None)
            if current != reservation:
                raise RuntimeError("quota reservation is stale or already released")
            now = self._clock()
            usage = self._current_usage(reservation.principal, now)
            updated = QuotaUsage(
                window_started_at=usage.window_started_at,
                starts=usage.starts,
                inflight=max(0, usage.inflight - 1),
                failures=usage.failures,
                output_bytes=usage.output_bytes,
            )
            self._usage[reservation.principal] = updated
            return updated

    def usage(self, principal: str) -> QuotaUsage:
        principal = self._validate_principal(principal)
        with self._lock:
            return self._current_usage(principal, self._clock())

    def active_reservations(self, principal: str | None = None) -> tuple[QuotaReservation, ...]:
        with self._lock:
            values = self._reservations.values()
            if principal is not None:
                values = (item for item in values if item.principal == principal)
            return tuple(sorted(values, key=lambda item: item.reservation_id))
