"""Shared runtime admission controller for expensive operations.

Pure admission in skeleton.intelligence.admission evaluates one request.
This module composes that contract with live process pressure and the existing
tenant quota ledger. It owns reservations for the lifetime of admitted work and
reconciles them when work completes.

The controller is deliberately provider-neutral: providers, tools, artifact
writers, and other expensive planes can share the same instance so concurrency
and tenant quota are not evaluated against isolated local counters.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import math
import threading
import time
from typing import Any

from skeleton.intelligence.admission import (
    AdmissionDecision,
    AdmissionError,
    AdmissionRequest,
    RuntimePressure,
    UsageEstimate,
    require_admission,
)
from skeleton.intelligence.quota import (
    QuotaCompletion,
    QuotaConflict,
    QuotaError,
    QuotaExceeded,
    QuotaReservation,
    QuotaUsageEvent,
    TenantQuotaLedger,
)


class AdmissionRuntimeError(RuntimeError):
    """Base mutable admission-runtime failure."""


class AdmissionRuntimeConflict(AdmissionRuntimeError):
    """Operation admission state conflicts with an active lease."""


def _wall_time(value: float | None, *, field: str) -> float:
    number = time.time() if value is None else float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return number


def _request_fingerprint(request: AdmissionRequest) -> str:
    material = "\x1f".join(
        (
            request.operation_id,
            request.tenant_id,
            request.capability,
            str(request.budget.as_dict()),
            str(request.estimate),
            str(request.priority),
            str(request.deadline_monotonic),
        )
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _lease_id(
    decision: AdmissionDecision,
    reservation: QuotaReservation | None,
) -> str:
    material = "\x1f".join(
        (
            decision.decision_id,
            reservation.reservation_id if reservation is not None else "",
        )
    ).encode("utf-8")
    return "lease-" + hashlib.sha256(material).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class AdmissionLease:
    lease_id: str
    decision: AdmissionDecision
    quota_reservation: QuotaReservation | None
    admitted_at: float

    @property
    def operation_id(self) -> str:
        return self.decision.operation_id

    @property
    def tenant_id(self) -> str:
        return self.decision.tenant_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "decision": self.decision.as_dict(),
            "quota_reservation_id": (
                None
                if self.quota_reservation is None
                else self.quota_reservation.reservation_id
            ),
            "admitted_at": self.admitted_at,
        }


@dataclass(frozen=True, slots=True)
class AdmissionCompletion:
    lease: AdmissionLease
    quota_completion: QuotaCompletion | None
    completed_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease.lease_id,
            "operation_id": self.lease.operation_id,
            "tenant_id": self.lease.tenant_id,
            "completed_at": self.completed_at,
            "quota": (
                None
                if self.quota_completion is None
                else self.quota_completion.as_dict()
            ),
        }


@dataclass(slots=True)
class _ActiveLease:
    lease: AdmissionLease
    request_fingerprint: str


class AdmissionRuntime:
    """Thread-safe shared pressure, quota reservation, and completion boundary."""

    def __init__(
        self,
        *,
        quota_ledger: TenantQuotaLedger | None = None,
    ) -> None:
        self.quota_ledger = quota_ledger
        self._lock = threading.RLock()
        self._active: dict[str, _ActiveLease] = {}
        self._queue_depth = 0

    @property
    def pressure(self) -> RuntimePressure:
        with self._lock:
            return RuntimePressure(
                active_operations=len(self._active),
                queue_depth=self._queue_depth,
            )

    def set_queue_depth(self, queue_depth: int) -> RuntimePressure:
        if (
            isinstance(queue_depth, bool)
            or not isinstance(queue_depth, int)
            or queue_depth < 0
        ):
            raise ValueError("queue_depth must be a non-negative integer")
        with self._lock:
            self._queue_depth = queue_depth
            return RuntimePressure(
                active_operations=len(self._active),
                queue_depth=self._queue_depth,
            )

    def admit(
        self,
        request: AdmissionRequest,
        *,
        now_monotonic: float | None = None,
        now_wall: float | None = None,
    ) -> AdmissionLease:
        if not isinstance(request, AdmissionRequest):
            raise TypeError("request must be an AdmissionRequest")
        wall = _wall_time(now_wall, field="now_wall")
        fingerprint = _request_fingerprint(request)

        with self._lock:
            current = self._active.get(request.operation_id)
            if current is not None:
                if current.request_fingerprint != fingerprint:
                    raise AdmissionRuntimeConflict(
                        "operation already has an active admission lease with different inputs"
                    )
                return current.lease

            pressure = RuntimePressure(
                active_operations=len(self._active),
                queue_depth=self._queue_depth,
            )
            evaluated = replace(request, pressure=pressure)
            decision = require_admission(
                evaluated,
                now_monotonic=now_monotonic,
            )

            reservation: QuotaReservation | None = None
            if self.quota_ledger is not None:
                try:
                    reservation = self.quota_ledger.reserve(
                        request.tenant_id,
                        request.operation_id,
                        request.estimate,
                        now=wall,
                    )
                except QuotaExceeded as exc:
                    raise AdmissionError(str(exc)) from exc
                except (QuotaConflict, QuotaError) as exc:
                    raise AdmissionError("tenant_quota_unavailable") from exc

            lease = AdmissionLease(
                lease_id=_lease_id(decision, reservation),
                decision=decision,
                quota_reservation=reservation,
                admitted_at=wall,
            )
            self._active[request.operation_id] = _ActiveLease(
                lease=lease,
                request_fingerprint=fingerprint,
            )
            return lease

    def record_usage_event(
        self,
        operation_id: str,
        event_id: str,
        category: str,
        delta: UsageEstimate,
        *,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        """Charge one idempotent actual-usage event against an active lease."""

        if not isinstance(delta, UsageEstimate):
            raise TypeError("delta must be a UsageEstimate")
        operation = str(operation_id).strip()
        if not operation:
            raise AdmissionRuntimeError("operation_id is required")
        wall = _wall_time(now_wall, field="now_wall")

        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise AdmissionRuntimeError(
                    "operation has no active admission lease"
                )
            reservation = active.lease.quota_reservation
            if reservation is None or self.quota_ledger is None:
                raise AdmissionRuntimeError(
                    "operation has no durable quota reservation"
                )
            recorder = getattr(self.quota_ledger, "record_usage_event", None)
            if not callable(recorder):
                raise AdmissionRuntimeError(
                    "quota ledger does not support incremental usage metering"
                )

            decision = active.lease.decision
            max_tool_calls = int(
                decision.estimated.tool_calls
                + int(decision.remaining["tool_calls"])
            )
            max_artifact_bytes = int(
                decision.estimated.artifact_bytes
                + int(decision.remaining["artifact_bytes"])
            )
            try:
                return recorder(
                    reservation.reservation_id,
                    event_id,
                    category,
                    delta,
                    max_tool_calls=max_tool_calls,
                    max_artifact_bytes=max_artifact_bytes,
                    now=wall,
                )
            except QuotaExceeded as exc:
                raise AdmissionError(str(exc)) from exc
            except QuotaConflict as exc:
                raise AdmissionRuntimeConflict(str(exc)) from exc
            except QuotaError as exc:
                raise AdmissionRuntimeError(
                    "incremental_usage_meter_unavailable"
                ) from exc

    def meter_tool_call(
        self,
        operation_id: str,
        event_id: str,
        *,
        calls: int = 1,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        if isinstance(calls, bool) or not isinstance(calls, int) or calls <= 0:
            raise ValueError("calls must be a positive integer")
        return self.record_usage_event(
            operation_id,
            event_id,
            "tool",
            UsageEstimate(tool_calls=calls),
            now_wall=now_wall,
        )

    def meter_artifact_bytes(
        self,
        operation_id: str,
        event_id: str,
        byte_count: int,
        *,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
        ):
            raise ValueError("byte_count must be a non-negative integer")
        return self.record_usage_event(
            operation_id,
            event_id,
            "artifact",
            UsageEstimate(artifact_bytes=byte_count),
            now_wall=now_wall,
        )

    def meter_storage_bytes(
        self,
        operation_id: str,
        event_id: str,
        byte_count: int,
        *,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
        ):
            raise ValueError("byte_count must be a non-negative integer")
        return self.record_usage_event(
            operation_id,
            event_id,
            "storage",
            UsageEstimate(artifact_bytes=byte_count),
            now_wall=now_wall,
        )

    def complete(
        self,
        operation_id: str,
        actual: UsageEstimate,
        *,
        now_wall: float | None = None,
    ) -> AdmissionCompletion:
        if not isinstance(actual, UsageEstimate):
            raise TypeError("actual must be a UsageEstimate")
        operation = str(operation_id).strip()
        if not operation:
            raise AdmissionRuntimeError("operation_id is required")
        wall = _wall_time(now_wall, field="now_wall")

        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise AdmissionRuntimeError("operation has no active admission lease")

            quota_completion: QuotaCompletion | None = None
            reservation = active.lease.quota_reservation
            if reservation is not None:
                if self.quota_ledger is None:
                    raise AdmissionRuntimeError(
                        "quota reservation exists without a quota ledger"
                    )
                quota_completion = self.quota_ledger.complete(
                    reservation.reservation_id,
                    actual,
                    now=wall,
                )

            self._active.pop(operation)
            return AdmissionCompletion(
                lease=active.lease,
                quota_completion=quota_completion,
                completed_at=wall,
            )

    def release(
        self,
        operation_id: str,
    ) -> AdmissionLease:
        operation = str(operation_id).strip()
        if not operation:
            raise AdmissionRuntimeError("operation_id is required")

        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise AdmissionRuntimeError("operation has no active admission lease")
            reservation = active.lease.quota_reservation
            if reservation is not None:
                if self.quota_ledger is None:
                    raise AdmissionRuntimeError(
                        "quota reservation exists without a quota ledger"
                    )
                self.quota_ledger.release(reservation.reservation_id)
            self._active.pop(operation)
            return active.lease

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pressure": {
                    "active_operations": len(self._active),
                    "queue_depth": self._queue_depth,
                },
                "active_operations": tuple(sorted(self._active)),
                "quota_enabled": self.quota_ledger is not None,
            }


__all__ = [
    "AdmissionCompletion",
    "AdmissionLease",
    "AdmissionRuntime",
    "AdmissionRuntimeConflict",
    "AdmissionRuntimeError",
]
