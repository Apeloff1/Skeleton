"""Tenant quota reservations and actual-usage reconciliation.

Resource admission answers whether one operation fits its local envelope.
This module adds the shared tenant/window dimension: reservations are atomic,
idempotent by operation ID, count against cumulative quota before expensive
work, and are reconciled against actual usage when work completes.

The ledger stores usage metadata only. Durable persistence can replace or wrap
this in-memory implementation without changing the reservation contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import threading
import time
from typing import Any

from skeleton.intelligence.admission import UsageEstimate


class QuotaError(RuntimeError):
    """Base tenant-quota failure."""


class QuotaExceeded(QuotaError):
    """A reservation cannot fit the tenant's configured quota."""


class QuotaConflict(QuotaError):
    """A reservation/window transition conflicts with active state."""


def _required_id(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QuotaError(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > 256:
        raise QuotaError(f"{field} is too long")
    return normalized


def _nonnegative_int(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QuotaError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: int, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value == 0:
        raise QuotaError(f"{field} must be greater than zero")
    return value


def _finite_nonnegative(value: float, field: str) -> float:
    if isinstance(value, bool):
        raise QuotaError(f"{field} must be finite and non-negative")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise QuotaError(f"{field} must be finite and non-negative")
    return number


@dataclass(frozen=True, slots=True)
class TenantQuota:
    window_id: str
    max_operations: int = 1_000
    max_input_tokens: int = 5_000_000
    max_output_tokens: int = 1_000_000
    max_cost_usd: float = 100.0
    max_tool_calls: int = 10_000
    max_artifact_bytes: int = 10 * 1024 * 1024 * 1024
    max_concurrent_operations: int = 32

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "window_id",
            _required_id(self.window_id, "window_id"),
        )
        for field in (
            "max_operations",
            "max_input_tokens",
            "max_output_tokens",
            "max_tool_calls",
            "max_artifact_bytes",
        ):
            _nonnegative_int(getattr(self, field), field)
        _positive_int(
            self.max_concurrent_operations,
            "max_concurrent_operations",
        )
        _finite_nonnegative(self.max_cost_usd, "max_cost_usd")


@dataclass(frozen=True, slots=True)
class QuotaUsage:
    operations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: int = 0
    artifact_bytes: int = 0

    def __post_init__(self) -> None:
        for field in (
            "operations",
            "input_tokens",
            "output_tokens",
            "tool_calls",
            "artifact_bytes",
        ):
            _nonnegative_int(getattr(self, field), field)
        _finite_nonnegative(self.cost_usd, "cost_usd")

    @classmethod
    def from_estimate(
        cls,
        estimate: UsageEstimate,
        *,
        operations: int = 1,
    ) -> "QuotaUsage":
        if not isinstance(estimate, UsageEstimate):
            raise QuotaError("estimate must be UsageEstimate")
        return cls(
            operations=operations,
            input_tokens=estimate.input_tokens,
            output_tokens=estimate.output_tokens,
            cost_usd=estimate.cost_usd,
            tool_calls=estimate.tool_calls,
            artifact_bytes=estimate.artifact_bytes,
        )

    def plus(self, other: "QuotaUsage") -> "QuotaUsage":
        return QuotaUsage(
            operations=self.operations + other.operations,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
            tool_calls=self.tool_calls + other.tool_calls,
            artifact_bytes=self.artifact_bytes + other.artifact_bytes,
        )

    def as_dict(self) -> dict[str, int | float]:
        return {
            "operations": self.operations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "tool_calls": self.tool_calls,
            "artifact_bytes": self.artifact_bytes,
        }


@dataclass(frozen=True, slots=True)
class QuotaReservation:
    reservation_id: str
    tenant_id: str
    window_id: str
    operation_id: str
    estimate: QuotaUsage
    reserved_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "reservation_id": self.reservation_id,
            "tenant_id": self.tenant_id,
            "window_id": self.window_id,
            "operation_id": self.operation_id,
            "estimate": self.estimate.as_dict(),
            "reserved_at": self.reserved_at,
        }


@dataclass(frozen=True, slots=True)
class QuotaUsageEvent:
    """Idempotent incremental actual-usage observation for one reservation."""

    event_id: str
    reservation_id: str
    tenant_id: str
    window_id: str
    operation_id: str
    category: str
    delta: QuotaUsage
    recorded_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "reservation_id": self.reservation_id,
            "tenant_id": self.tenant_id,
            "window_id": self.window_id,
            "operation_id": self.operation_id,
            "category": self.category,
            "delta": self.delta.as_dict(),
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True, slots=True)
class QuotaCompletion:
    reservation_id: str
    tenant_id: str
    window_id: str
    operation_id: str
    estimate: QuotaUsage
    actual: QuotaUsage
    overrun_dimensions: tuple[str, ...]
    completed_at: float

    @property
    def overrun(self) -> bool:
        return bool(self.overrun_dimensions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "reservation_id": self.reservation_id,
            "tenant_id": self.tenant_id,
            "window_id": self.window_id,
            "operation_id": self.operation_id,
            "estimate": self.estimate.as_dict(),
            "actual": self.actual.as_dict(),
            "overrun": self.overrun,
            "overrun_dimensions": list(self.overrun_dimensions),
            "completed_at": self.completed_at,
        }


@dataclass(slots=True)
class _TenantState:
    quota: TenantQuota
    committed: QuotaUsage
    reservations: dict[str, QuotaReservation]
    by_operation: dict[str, str]
    completions: list[QuotaCompletion]


def _reservation_id(
    tenant_id: str,
    window_id: str,
    operation_id: str,
    estimate: QuotaUsage,
) -> str:
    material = "\x1f".join(
        (
            tenant_id,
            window_id,
            operation_id,
            str(estimate.as_dict()),
        )
    ).encode("utf-8")
    return "qrs-" + hashlib.sha256(material).hexdigest()[:24]


def _quota_excess(
    quota: TenantQuota,
    usage: QuotaUsage,
) -> tuple[str, ...]:
    excess: list[str] = []
    if usage.operations > quota.max_operations:
        excess.append("operations")
    if usage.input_tokens > quota.max_input_tokens:
        excess.append("input_tokens")
    if usage.output_tokens > quota.max_output_tokens:
        excess.append("output_tokens")
    if usage.cost_usd > quota.max_cost_usd:
        excess.append("cost_usd")
    if usage.tool_calls > quota.max_tool_calls:
        excess.append("tool_calls")
    if usage.artifact_bytes > quota.max_artifact_bytes:
        excess.append("artifact_bytes")
    return tuple(excess)


class TenantQuotaLedger:
    """Thread-safe reservation ledger for one or more tenant quota windows."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, _TenantState] = {}

    def configure(
        self,
        tenant_id: str,
        quota: TenantQuota,
        *,
        replace: bool = False,
    ) -> TenantQuota:
        tenant = _required_id(tenant_id, "tenant_id")
        if not isinstance(quota, TenantQuota):
            raise QuotaError("quota must be TenantQuota")
        with self._lock:
            current = self._states.get(tenant)
            if current is not None:
                if not replace:
                    raise QuotaConflict("tenant quota already configured")
                if current.reservations:
                    raise QuotaConflict(
                        "cannot replace quota while reservations are active"
                    )
            self._states[tenant] = _TenantState(
                quota=quota,
                committed=QuotaUsage(),
                reservations={},
                by_operation={},
                completions=[],
            )
        return quota

    def _state(self, tenant_id: str) -> _TenantState:
        tenant = _required_id(tenant_id, "tenant_id")
        try:
            return self._states[tenant]
        except KeyError as exc:
            raise QuotaError("tenant quota is not configured") from exc

    @staticmethod
    def _reserved_usage(state: _TenantState) -> QuotaUsage:
        total = QuotaUsage()
        for reservation in state.reservations.values():
            total = total.plus(reservation.estimate)
        return total

    def reserve(
        self,
        tenant_id: str,
        operation_id: str,
        estimate: UsageEstimate,
        *,
        now: float | None = None,
    ) -> QuotaReservation:
        tenant = _required_id(tenant_id, "tenant_id")
        operation = _required_id(operation_id, "operation_id")
        if not isinstance(estimate, UsageEstimate):
            raise QuotaError("estimate must be UsageEstimate")
        timestamp = time.time() if now is None else _finite_nonnegative(now, "now")
        requested = QuotaUsage.from_estimate(estimate)

        with self._lock:
            state = self._state(tenant)
            existing_id = state.by_operation.get(operation)
            if existing_id is not None:
                existing = state.reservations.get(existing_id)
                if existing is not None:
                    if existing.estimate != requested:
                        raise QuotaConflict(
                            "operation already reserved with a different estimate"
                        )
                    return existing
                for completion in state.completions:
                    if completion.operation_id == operation:
                        raise QuotaConflict("operation quota reservation already completed")

            if len(state.reservations) >= state.quota.max_concurrent_operations:
                raise QuotaExceeded("tenant_concurrency_exceeded")

            projected = (
                state.committed
                .plus(self._reserved_usage(state))
                .plus(requested)
            )
            excess = _quota_excess(state.quota, projected)
            if excess:
                raise QuotaExceeded(
                    "tenant_quota_exceeded:" + ",".join(excess)
                )

            reservation = QuotaReservation(
                reservation_id=_reservation_id(
                    tenant,
                    state.quota.window_id,
                    operation,
                    requested,
                ),
                tenant_id=tenant,
                window_id=state.quota.window_id,
                operation_id=operation,
                estimate=requested,
                reserved_at=timestamp,
            )
            state.reservations[reservation.reservation_id] = reservation
            state.by_operation[operation] = reservation.reservation_id
            return reservation

    def release(self, reservation_id: str) -> QuotaReservation:
        key = _required_id(reservation_id, "reservation_id")
        with self._lock:
            for state in self._states.values():
                reservation = state.reservations.pop(key, None)
                if reservation is None:
                    continue
                state.by_operation.pop(reservation.operation_id, None)
                return reservation
        raise QuotaError("unknown active quota reservation")

    def complete(
        self,
        reservation_id: str,
        actual: UsageEstimate,
        *,
        now: float | None = None,
    ) -> QuotaCompletion:
        key = _required_id(reservation_id, "reservation_id")
        if not isinstance(actual, UsageEstimate):
            raise QuotaError("actual must be UsageEstimate")
        timestamp = time.time() if now is None else _finite_nonnegative(now, "now")
        actual_usage = QuotaUsage.from_estimate(actual)

        with self._lock:
            matched_state: _TenantState | None = None
            reservation: QuotaReservation | None = None
            for state in self._states.values():
                candidate = state.reservations.get(key)
                if candidate is not None:
                    matched_state = state
                    reservation = candidate
                    break
            if matched_state is None or reservation is None:
                raise QuotaError("unknown active quota reservation")

            projected = matched_state.committed.plus(actual_usage)
            overruns = _quota_excess(matched_state.quota, projected)
            completion = QuotaCompletion(
                reservation_id=reservation.reservation_id,
                tenant_id=reservation.tenant_id,
                window_id=reservation.window_id,
                operation_id=reservation.operation_id,
                estimate=reservation.estimate,
                actual=actual_usage,
                overrun_dimensions=overruns,
                completed_at=timestamp,
            )
            matched_state.reservations.pop(key)
            matched_state.committed = projected
            matched_state.completions.append(completion)
            return completion

    def snapshot(self, tenant_id: str) -> dict[str, Any]:
        tenant = _required_id(tenant_id, "tenant_id")
        with self._lock:
            state = self._state(tenant)
            reserved = self._reserved_usage(state)
            projected = state.committed.plus(reserved)
            return {
                "tenant_id": tenant,
                "window_id": state.quota.window_id,
                "quota": {
                    "max_operations": state.quota.max_operations,
                    "max_input_tokens": state.quota.max_input_tokens,
                    "max_output_tokens": state.quota.max_output_tokens,
                    "max_cost_usd": state.quota.max_cost_usd,
                    "max_tool_calls": state.quota.max_tool_calls,
                    "max_artifact_bytes": state.quota.max_artifact_bytes,
                    "max_concurrent_operations": state.quota.max_concurrent_operations,
                },
                "committed": state.committed.as_dict(),
                "reserved": reserved.as_dict(),
                "projected": projected.as_dict(),
                "active_reservations": len(state.reservations),
                "completions": len(state.completions),
                "over_quota_dimensions": list(
                    _quota_excess(state.quota, projected)
                ),
            }

    def reset_window(
        self,
        tenant_id: str,
        quota: TenantQuota,
    ) -> TenantQuota:
        tenant = _required_id(tenant_id, "tenant_id")
        if not isinstance(quota, TenantQuota):
            raise QuotaError("quota must be TenantQuota")
        with self._lock:
            state = self._state(tenant)
            if state.reservations:
                raise QuotaConflict(
                    "cannot reset quota window while reservations are active"
                )
            if quota.window_id == state.quota.window_id:
                raise QuotaConflict("new quota window_id must change")
            self._states[tenant] = _TenantState(
                quota=quota,
                committed=QuotaUsage(),
                reservations={},
                by_operation={},
                completions=[],
            )
        return quota


__all__ = [
    "QuotaCompletion",
    "QuotaConflict",
    "QuotaError",
    "QuotaExceeded",
    "QuotaReservation",
    "QuotaUsage",
    "QuotaUsageEvent",
    "TenantQuota",
    "TenantQuotaLedger",
]
