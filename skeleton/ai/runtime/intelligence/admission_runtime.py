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

from skeleton.cognition.telemetry import MetricRegistry
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
    TenantQuota,
    TenantQuotaLedger,
)
from skeleton.intelligence.shared_pressure import (
    SharedPressureConflict,
    SharedPressureError,
    SharedPressureExceeded,
    SharedPressureLease,
    SqliteSharedPressureLedger,
)


class AdmissionRuntimeError(RuntimeError):
    """Base mutable admission-runtime failure."""


class AdmissionRuntimeConflict(AdmissionRuntimeError):
    """Operation admission state conflicts with an active lease."""


_USAGE_CATEGORIES = {"tool", "artifact", "storage", "provider", "other"}
_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "wall_seconds",
    "provider_attempts",
    "tool_calls",
    "artifact_bytes",
    "storage_bytes",
)


def _observe_usage(
    metrics: MetricRegistry,
    prefix: str,
    usage: UsageEstimate,
) -> None:
    for field_name in _USAGE_FIELDS:
        metrics.observe(
            f"admission.{prefix}.{field_name}",
            float(getattr(usage, field_name)),
        )


def _observe_usage_delta(
    metrics: MetricRegistry,
    estimated: UsageEstimate,
    actual: UsageEstimate,
) -> None:
    for field_name in _USAGE_FIELDS:
        metrics.observe(
            f"admission.delta.{field_name}",
            float(getattr(actual, field_name))
            - float(getattr(estimated, field_name)),
        )


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


@dataclass(frozen=True, slots=True)
class UnknownUsageMarker:
    event_id: str
    operation_id: str
    category: str
    reason: str
    recorded_at: float


@dataclass(slots=True)
class _ActiveLease:
    lease: AdmissionLease
    request_fingerprint: str
    unknown_usage: dict[str, UnknownUsageMarker]
    shared_pressure_lease: SharedPressureLease | None = None


class AdmissionRuntime:
    """Thread-safe shared pressure, quota reservation, and completion boundary."""

    def __init__(
        self,
        *,
        quota_ledger: TenantQuotaLedger | None = None,
        default_tenant_quota: TenantQuota | None = None,
        metrics_registry: MetricRegistry | None = None,
        shared_pressure_ledger: SqliteSharedPressureLedger | None = None,
        shared_pressure_scope: str | None = None,
        shared_pressure_owner_id: str | None = None,
    ) -> None:
        pressure_values = (
            shared_pressure_ledger,
            shared_pressure_scope,
            shared_pressure_owner_id,
        )
        if any(value is not None for value in pressure_values) and not all(
            value is not None for value in pressure_values
        ):
            raise ValueError(
                "shared pressure ledger, scope, and owner_id must be configured together"
            )
        if default_tenant_quota is not None and quota_ledger is None:
            raise ValueError(
                "default_tenant_quota requires quota_ledger"
            )
        if (
            default_tenant_quota is not None
            and not isinstance(default_tenant_quota, TenantQuota)
        ):
            raise TypeError("default_tenant_quota must be TenantQuota")
        self.quota_ledger = quota_ledger
        self.default_tenant_quota = default_tenant_quota
        self.metrics_registry = metrics_registry or MetricRegistry()
        self.shared_pressure_ledger = shared_pressure_ledger
        self.shared_pressure_scope = (
            None
            if shared_pressure_scope is None
            else str(shared_pressure_scope).strip()
        )
        self.shared_pressure_owner_id = (
            None
            if shared_pressure_owner_id is None
            else str(shared_pressure_owner_id).strip()
        )
        if shared_pressure_ledger is not None and (
            not self.shared_pressure_scope
            or not self.shared_pressure_owner_id
        ):
            raise ValueError(
                "shared pressure scope and owner_id must be non-empty"
            )
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

    def _ensure_tenant_quota(self, tenant_id: str) -> None:
        if self.quota_ledger is None or self.default_tenant_quota is None:
            return
        try:
            self.quota_ledger.snapshot(tenant_id)
            return
        except QuotaError:
            pass
        try:
            self.quota_ledger.configure(
                tenant_id,
                self.default_tenant_quota,
            )
        except QuotaConflict:
            # Another worker may have won first-use provisioning.
            try:
                self.quota_ledger.snapshot(tenant_id)
            except QuotaError as exc:
                raise AdmissionRuntimeError(
                    "tenant_quota_unavailable"
                ) from exc
        except QuotaError as exc:
            raise AdmissionRuntimeError(
                "tenant_quota_unavailable"
            ) from exc

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

            shared_snapshot = None
            if self.shared_pressure_ledger is not None:
                try:
                    shared_snapshot = self.shared_pressure_ledger.snapshot(
                        self.shared_pressure_scope,
                        tenant_id=request.tenant_id,
                        now=wall,
                    )
                except SharedPressureError as exc:
                    raise AdmissionRuntimeError(
                        "shared_pressure_unavailable"
                    ) from exc

            pressure = RuntimePressure(
                active_operations=max(
                    len(self._active),
                    0 if shared_snapshot is None else shared_snapshot.active,
                ),
                queue_depth=max(
                    self._queue_depth,
                    0 if shared_snapshot is None else shared_snapshot.queued,
                ),
            )
            evaluated = replace(request, pressure=pressure)
            decision = require_admission(
                evaluated,
                now_monotonic=now_monotonic,
            )

            shared_lease: SharedPressureLease | None = None
            if self.shared_pressure_ledger is not None:
                try:
                    shared_lease = self.shared_pressure_ledger.acquire(
                        self.shared_pressure_scope,
                        request.tenant_id,
                        request.operation_id,
                        self.shared_pressure_owner_id,
                        priority=request.priority,
                        lease_seconds=request.budget.max_wall_seconds,
                        now=wall,
                    )
                except SharedPressureExceeded as exc:
                    raise AdmissionError(str(exc)) from exc
                except SharedPressureConflict as exc:
                    raise AdmissionRuntimeConflict(str(exc)) from exc
                except SharedPressureError as exc:
                    raise AdmissionRuntimeError(
                        "shared_pressure_unavailable"
                    ) from exc

            reservation: QuotaReservation | None = None
            if self.quota_ledger is not None:
                self._ensure_tenant_quota(request.tenant_id)
                try:
                    reservation = self.quota_ledger.reserve(
                        request.tenant_id,
                        request.operation_id,
                        request.estimate,
                        now=wall,
                    )
                except QuotaExceeded as exc:
                    if shared_lease is not None:
                        self._release_shared_pressure(shared_lease)
                    raise AdmissionError(str(exc)) from exc
                except (QuotaConflict, QuotaError) as exc:
                    if shared_lease is not None:
                        self._release_shared_pressure(shared_lease)
                    raise AdmissionError("tenant_quota_unavailable") from exc

            lease = AdmissionLease(
                lease_id=_lease_id(decision, reservation),
                decision=decision,
                quota_reservation=reservation,
                admitted_at=wall,
            )
            self.metrics_registry.inc("admission.admitted_total")
            _observe_usage(
                self.metrics_registry,
                "estimated",
                decision.estimated,
            )
            self._active[request.operation_id] = _ActiveLease(
                lease=lease,
                request_fingerprint=fingerprint,
                unknown_usage={},
                shared_pressure_lease=shared_lease,
            )
            return lease

    def _release_shared_pressure(
        self,
        lease: SharedPressureLease,
    ) -> None:
        ledger = self.shared_pressure_ledger
        owner = self.shared_pressure_owner_id
        if ledger is None or owner is None:
            return
        try:
            ledger.release(lease.lease_id, owner)
        except SharedPressureError:
            # Shared pressure leases are time-bounded. Terminal accounting must
            # not become unrecoverable because an already-expired pressure lease
            # was reaped by another worker.
            self.metrics_registry.inc(
                "admission.shared_pressure_release_error_total"
            )

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
            max_storage_bytes = int(
                decision.estimated.storage_bytes
                + int(decision.remaining["storage_bytes"])
            )
            try:
                return recorder(
                    reservation.reservation_id,
                    event_id,
                    category,
                    delta,
                    max_tool_calls=max_tool_calls,
                    max_artifact_bytes=max_artifact_bytes,
                    max_storage_bytes=max_storage_bytes,
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
            UsageEstimate(storage_bytes=byte_count),
            now_wall=now_wall,
        )

    def mark_usage_unknown(
        self,
        operation_id: str,
        event_id: str,
        category: str,
        reason: str,
        *,
        now_wall: float | None = None,
    ) -> UnknownUsageMarker:
        """Record unresolved actual usage and block completion/release.

        Unknown usage is never treated as zero. Callers must resolve it with a
        conservative measured charge before the operation can reach a terminal
        accounting state.
        """

        operation = str(operation_id).strip()
        event = str(event_id).strip()
        normalized_category = str(category).strip().lower()
        normalized_reason = str(reason).strip()
        if not operation:
            raise AdmissionRuntimeError("operation_id is required")
        if not event:
            raise AdmissionRuntimeError("event_id is required")
        if normalized_category not in _USAGE_CATEGORIES:
            raise AdmissionRuntimeError("unsupported usage category")
        if not normalized_reason:
            raise AdmissionRuntimeError("unknown usage reason is required")
        wall = _wall_time(now_wall, field="now_wall")

        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise AdmissionRuntimeError(
                    "operation has no active admission lease"
                )
            reservation = active.lease.quota_reservation
            if reservation is not None:
                if self.quota_ledger is None:
                    raise AdmissionRuntimeError(
                        "quota reservation exists without a quota ledger"
                    )
                marker_writer = getattr(self.quota_ledger, "mark_usage_unknown", None)
                if not callable(marker_writer):
                    raise AdmissionRuntimeError(
                        "quota ledger does not support durable unknown usage"
                    )
                try:
                    marker_writer(
                        reservation.reservation_id,
                        event,
                        normalized_category,
                        now=wall,
                    )
                except QuotaConflict as exc:
                    raise AdmissionRuntimeConflict(str(exc)) from exc
                except QuotaError as exc:
                    raise AdmissionRuntimeError(
                        "unknown_usage_marker_unavailable"
                    ) from exc

            existing = active.unknown_usage.get(event)
            if existing is not None:
                if (
                    existing.category != normalized_category
                    or existing.reason != normalized_reason
                ):
                    raise AdmissionRuntimeConflict(
                        "unknown usage event replayed with different inputs"
                    )
                return existing
            marker = UnknownUsageMarker(
                event_id=event,
                operation_id=operation,
                category=normalized_category,
                reason=normalized_reason,
                recorded_at=wall,
            )
            active.unknown_usage[event] = marker
            return marker

    def resolve_unknown_usage(
        self,
        operation_id: str,
        event_id: str,
        delta: UsageEstimate,
        *,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        """Resolve an unknown-usage marker with a conservative metered charge."""

        operation = str(operation_id).strip()
        event = str(event_id).strip()
        if not isinstance(delta, UsageEstimate):
            raise TypeError("delta must be a UsageEstimate")
        if not operation:
            raise AdmissionRuntimeError("operation_id is required")
        if not event:
            raise AdmissionRuntimeError("event_id is required")

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
            resolver = getattr(self.quota_ledger, "resolve_unknown_usage", None)
            if not callable(resolver):
                raise AdmissionRuntimeError(
                    "quota ledger does not support durable unknown usage"
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
            max_storage_bytes = int(
                decision.estimated.storage_bytes
                + int(decision.remaining["storage_bytes"])
            )
            try:
                recorded = resolver(
                    reservation.reservation_id,
                    event,
                    delta,
                    max_tool_calls=max_tool_calls,
                    max_artifact_bytes=max_artifact_bytes,
                    max_storage_bytes=max_storage_bytes,
                    now=_wall_time(now_wall, field="now_wall"),
                )
            except QuotaExceeded as exc:
                raise AdmissionError(str(exc)) from exc
            except QuotaConflict as exc:
                raise AdmissionRuntimeConflict(str(exc)) from exc
            except QuotaError as exc:
                raise AdmissionRuntimeError(
                    "unknown_usage_resolution_unavailable"
                ) from exc
            active.unknown_usage.pop(event, None)
            return recorded

    @staticmethod
    def _unknown_usage_error(active: _ActiveLease) -> str | None:
        if not active.unknown_usage:
            return None
        categories = sorted({item.category for item in active.unknown_usage.values()})
        return "actual_usage_unknown:" + ",".join(categories)

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
            unknown_error = self._unknown_usage_error(active)
            if unknown_error is not None:
                raise AdmissionRuntimeError(unknown_error)

            quota_completion: QuotaCompletion | None = None
            reservation = active.lease.quota_reservation
            if reservation is not None:
                if self.quota_ledger is None:
                    raise AdmissionRuntimeError(
                        "quota reservation exists without a quota ledger"
                    )
                try:
                    quota_completion = self.quota_ledger.complete(
                        reservation.reservation_id,
                        actual,
                        now=wall,
                    )
                except QuotaConflict as exc:
                    if str(exc).startswith("actual_usage_unknown:"):
                        raise AdmissionRuntimeError(str(exc)) from exc
                    raise AdmissionRuntimeConflict(str(exc)) from exc
                except QuotaError as exc:
                    raise AdmissionRuntimeError(
                        "quota_completion_unavailable"
                    ) from exc

            if active.shared_pressure_lease is not None:
                self._release_shared_pressure(
                    active.shared_pressure_lease
                )
            self.metrics_registry.inc("admission.completed_total")
            _observe_usage(
                self.metrics_registry,
                "actual",
                actual,
            )
            _observe_usage_delta(
                self.metrics_registry,
                active.lease.decision.estimated,
                actual,
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
            unknown_error = self._unknown_usage_error(active)
            if unknown_error is not None:
                raise AdmissionRuntimeError(unknown_error)
            reservation = active.lease.quota_reservation
            if reservation is not None:
                if self.quota_ledger is None:
                    raise AdmissionRuntimeError(
                        "quota reservation exists without a quota ledger"
                    )
                self.quota_ledger.release(reservation.reservation_id)
            if active.shared_pressure_lease is not None:
                self._release_shared_pressure(active.shared_pressure_lease)
            self._active.pop(operation)
            return active.lease

    def telemetry_snapshot(self) -> dict[str, Any]:
        """Return aggregate resource telemetry without operation or tenant IDs."""

        with self._lock:
            return {
                "schema_version": 1,
                "metrics": self.metrics_registry.snapshot(),
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pressure": {
                    "active_operations": len(self._active),
                    "queue_depth": self._queue_depth,
                },
                "active_operations": tuple(sorted(self._active)),
                "unknown_usage_events": sum(
                    len(active.unknown_usage)
                    for active in self._active.values()
                ),
                "unknown_usage_operations": tuple(
                    sorted(
                        operation_id
                        for operation_id, active in self._active.items()
                        if active.unknown_usage
                    )
                ),
                "quota_enabled": self.quota_ledger is not None,
            }


__all__ = [
    "AdmissionCompletion",
    "AdmissionLease",
    "AdmissionRuntime",
    "AdmissionRuntimeConflict",
    "AdmissionRuntimeError",
    "UnknownUsageMarker",
]
