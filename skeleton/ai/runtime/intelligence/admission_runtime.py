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
from typing import Any, Callable

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
_UNKNOWN_USAGE_PREFIX = "unknown:"
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


def _effective_actual_usage(
    reported: UsageEstimate,
    quota_completion: QuotaCompletion | None,
) -> UsageEstimate:
    """Join reported runtime usage with any larger durable metered usage."""

    if quota_completion is None:
        return reported
    observed = quota_completion.actual
    return UsageEstimate(
        input_tokens=max(reported.input_tokens, observed.input_tokens),
        output_tokens=max(reported.output_tokens, observed.output_tokens),
        cost_usd=max(reported.cost_usd, observed.cost_usd),
        wall_seconds=reported.wall_seconds,
        provider_attempts=reported.provider_attempts,
        tool_calls=max(reported.tool_calls, observed.tool_calls),
        artifact_bytes=max(
            reported.artifact_bytes,
            observed.artifact_bytes,
        ),
        storage_bytes=max(
            reported.storage_bytes,
            observed.storage_bytes,
        ),
    )


def _operation_budget_overruns(
    decision: AdmissionDecision,
    actual: UsageEstimate,
) -> tuple[str, ...]:
    """Return operation-budget dimensions exceeded by terminal actual usage."""

    limits: dict[str, int | float] = {
        field: (
            getattr(decision.estimated, field)
            + decision.remaining[field]
        )
        for field in _USAGE_FIELDS
    }
    exceeded: list[str] = []
    for field in _USAGE_FIELDS:
        value = getattr(actual, field)
        limit = limits[field]
        if field in {"cost_usd", "wall_seconds"}:
            if float(value) > float(limit) + 1e-12:
                exceeded.append(field)
        elif int(value) > int(limit):
            exceeded.append(field)
    return tuple(exceeded)


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


def admission_lease_id(
    decision: AdmissionDecision,
    reservation: QuotaReservation | None,
) -> str:
    """Return the deterministic identity of an admission + quota lease."""

    if not isinstance(decision, AdmissionDecision):
        raise TypeError("decision must be AdmissionDecision")
    if reservation is not None and not isinstance(
        reservation,
        QuotaReservation,
    ):
        raise TypeError("reservation must be QuotaReservation")
    material = "\x1f".join(
        (
            decision.decision_id,
            reservation.reservation_id if reservation is not None else "",
        )
    ).encode("utf-8")
    return "lease-" + hashlib.sha256(material).hexdigest()[:24]


def _lease_id(
    decision: AdmissionDecision,
    reservation: QuotaReservation | None,
) -> str:
    return admission_lease_id(decision, reservation)


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
    effective_actual: UsageEstimate | None = None
    operation_overrun_dimensions: tuple[str, ...] = ()

    @property
    def operation_overrun(self) -> bool:
        return bool(self.operation_overrun_dimensions)

    def as_dict(self) -> dict[str, Any]:
        actual = self.effective_actual
        return {
            "lease_id": self.lease.lease_id,
            "operation_id": self.lease.operation_id,
            "tenant_id": self.lease.tenant_id,
            "completed_at": self.completed_at,
            "effective_actual": (
                None
                if actual is None
                else {
                    field: getattr(actual, field)
                    for field in _USAGE_FIELDS
                }
            ),
            "operation_overrun_dimensions": list(
                self.operation_overrun_dimensions
            ),
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

    def ensure_tenant_quota(self, tenant_id: str) -> None:
        """Materialize default quota configuration without allocating authority.

        Durable recovery/preflight may need to inspect a tenant before a fresh
        reservation exists. Creating the tenant's configured quota is metadata
        initialization only: it does not reserve concurrency, tokens, cost,
        tool calls, artifact bytes, or storage bytes.
        """

        tenant = str(tenant_id).strip()
        if not tenant:
            raise AdmissionRuntimeError("tenant_id is required")
        with self._lock:
            self._ensure_tenant_quota(tenant)

    def admit(
        self,
        request: AdmissionRequest,
        *,
        now_monotonic: float | None = None,
        now_wall: float | None = None,
        decision_sink: Callable[
            [AdmissionDecision, float],
            None,
        ] | None = None,
    ) -> AdmissionLease:
        if not isinstance(request, AdmissionRequest):
            raise TypeError("request must be an AdmissionRequest")
        if decision_sink is not None and not callable(decision_sink):
            raise TypeError("decision_sink must be callable")
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
            if decision_sink is not None:
                try:
                    decision_sink(decision, wall)
                except Exception as exc:
                    raise AdmissionRuntimeError(
                        "admission_decision_persistence_failed"
                    ) from exc

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

    def shared_pressure_lease_for_operation(
        self,
        operation_id: str,
    ) -> SharedPressureLease | None:
        """Return the process-local shared-pressure receipt for active work."""

        operation = str(operation_id).strip()
        if not operation:
            raise AdmissionRuntimeError("operation_id is required")
        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise AdmissionRuntimeError(
                    "operation has no active admission lease"
                )
            return active.shared_pressure_lease

    def require_effect_authority(
        self,
        operation_id: str,
        *,
        now_wall: float | None = None,
    ) -> AdmissionLease:
        """Require live authority immediately before an external effect.

        Terminal accounting is intentionally not gated by this method: callers
        must still be able to reconcile actual usage after a slow or ambiguous
        effect. Effectful boundaries should call this immediately before
        dispatch so an expired durable pressure lease cannot authorize new work.
        """

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
            shared = active.shared_pressure_lease
            ledger = self.shared_pressure_ledger
            if ledger is None:
                if shared is not None:
                    raise AdmissionRuntimeConflict(
                        "active shared pressure lease has no configured ledger"
                    )
                return active.lease
            if shared is None:
                raise AdmissionRuntimeError(
                    "effect authority requires shared pressure lease"
                )
            finder = getattr(ledger, "lease_for_operation", None)
            if not callable(finder):
                raise AdmissionRuntimeError(
                    "shared pressure ledger does not support live authority lookup"
                )
            try:
                persisted = finder(
                    self.shared_pressure_scope,
                    operation,
                    now=wall,
                )
            except SharedPressureError as exc:
                raise AdmissionRuntimeError(
                    "effect_authority_unavailable"
                ) from exc
            if persisted is None:
                raise AdmissionRuntimeConflict(
                    "effect authority expired"
                )
            if persisted != shared:
                raise AdmissionRuntimeConflict(
                    "effect authority does not match active lease"
                )
            return active.lease

    def reattach(
        self,
        request: AdmissionRequest,
        lease: AdmissionLease,
        *,
        shared_pressure_lease: SharedPressureLease | None = None,
        now_wall: float | None = None,
    ) -> AdmissionLease:
        """Restore an already-durable lease without re-running admission.

        This is deliberately narrower than admit. It may only restore a lease
        whose quota reservation still exists exactly in the configured ledger.
        No quota is reserved and current local pressure is not used to
        invalidate work already durably admitted before restart.
        """

        if not isinstance(request, AdmissionRequest):
            raise TypeError("request must be an AdmissionRequest")
        if not isinstance(lease, AdmissionLease):
            raise TypeError("lease must be an AdmissionLease")
        if (
            shared_pressure_lease is not None
            and not isinstance(shared_pressure_lease, SharedPressureLease)
        ):
            raise TypeError(
                "shared_pressure_lease must be SharedPressureLease"
            )
        wall = _wall_time(now_wall, field="now_wall")
        if self.shared_pressure_ledger is None:
            if shared_pressure_lease is not None:
                raise AdmissionRuntimeConflict(
                    "recovered shared pressure lease has no configured ledger"
                )
        else:
            if shared_pressure_lease is None:
                raise AdmissionRuntimeError(
                    "shared_pressure_reattach_requires_durable_lease_metadata"
                )
            if (
                shared_pressure_lease.scope != self.shared_pressure_scope
                or shared_pressure_lease.operation_id != request.operation_id
                or shared_pressure_lease.tenant_id != request.tenant_id
                or shared_pressure_lease.owner_id
                != self.shared_pressure_owner_id
                or shared_pressure_lease.priority != request.priority
            ):
                raise AdmissionRuntimeConflict(
                    "durable shared pressure lease identity does not match runtime"
                )
        if self.quota_ledger is None or lease.quota_reservation is None:
            raise AdmissionRuntimeError(
                "durable_reattach_requires_quota_reservation"
            )
        if (
            lease.operation_id != request.operation_id
            or lease.tenant_id != request.tenant_id
            or lease.decision.capability != request.capability
        ):
            raise AdmissionRuntimeConflict(
                "durable lease identity does not match request"
            )
        if not lease.decision.admitted:
            raise AdmissionRuntimeConflict(
                "durable lease is not an admitted decision"
            )
        if lease.decision.estimated != request.estimate:
            raise AdmissionRuntimeConflict(
                "durable lease estimate does not match request"
            )

        remaining = lease.decision.remaining
        required_remaining = {
            "input_tokens": max(
                0,
                request.budget.max_input_tokens
                - request.estimate.input_tokens,
            ),
            "output_tokens": max(
                0,
                request.budget.max_output_tokens
                - request.estimate.output_tokens,
            ),
            "cost_usd": max(
                0.0,
                request.budget.max_cost_usd
                - request.estimate.cost_usd,
            ),
            "wall_seconds": max(
                0.0,
                request.budget.max_wall_seconds
                - request.estimate.wall_seconds,
            ),
            "provider_attempts": max(
                0,
                request.budget.max_provider_attempts
                - request.estimate.provider_attempts,
            ),
            "tool_calls": max(
                0,
                request.budget.max_tool_calls
                - request.estimate.tool_calls,
            ),
            "artifact_bytes": max(
                0,
                request.budget.max_artifact_bytes
                - request.estimate.artifact_bytes,
            ),
            "storage_bytes": max(
                0,
                request.budget.max_storage_bytes
                - request.estimate.storage_bytes,
            ),
        }
        expected_remaining_keys = set(required_remaining) | {
            "concurrency",
            "queue_depth",
        }
        if set(remaining) != expected_remaining_keys:
            raise AdmissionRuntimeConflict(
                "durable lease remaining budget fields do not match request"
            )
        for field, expected in required_remaining.items():
            if remaining[field] != expected:
                raise AdmissionRuntimeConflict(
                    "durable lease remaining budget does not match request"
                )
        concurrency = remaining["concurrency"]
        queue_depth = remaining["queue_depth"]
        if (
            isinstance(concurrency, bool)
            or not isinstance(concurrency, int)
            or concurrency < 0
            or concurrency > request.budget.max_concurrency
            or isinstance(queue_depth, bool)
            or not isinstance(queue_depth, int)
            or queue_depth < 0
            or queue_depth > request.budget.max_queue_depth
        ):
            raise AdmissionRuntimeConflict(
                "durable lease pressure remainder is invalid"
            )

        reservation = lease.quota_reservation
        if (
            reservation.operation_id != request.operation_id
            or reservation.tenant_id != request.tenant_id
        ):
            raise AdmissionRuntimeConflict(
                "durable quota reservation identity does not match request"
            )
        if lease.lease_id != _lease_id(
            lease.decision,
            reservation,
        ):
            raise AdmissionRuntimeConflict(
                "durable lease id does not match decision and reservation"
            )
        expected_quota = reservation.estimate
        if (
            expected_quota.operations != 1
            or expected_quota.input_tokens != request.estimate.input_tokens
            or expected_quota.output_tokens != request.estimate.output_tokens
            or expected_quota.cost_usd != request.estimate.cost_usd
            or expected_quota.tool_calls != request.estimate.tool_calls
            or expected_quota.artifact_bytes != request.estimate.artifact_bytes
            or expected_quota.storage_bytes != request.estimate.storage_bytes
        ):
            raise AdmissionRuntimeConflict(
                "durable quota estimate does not match request"
            )

        recovery_reader = getattr(
            self.quota_ledger,
            "recovery_state_for_operation",
            None,
        )
        if not callable(recovery_reader):
            raise AdmissionRuntimeError(
                "quota ledger does not support atomic durable recovery lookup"
            )

        fingerprint = _request_fingerprint(request)
        with self._lock:
            current = self._active.get(request.operation_id)
            if current is not None:
                if (
                    current.request_fingerprint != fingerprint
                    or current.lease != lease
                    or current.shared_pressure_lease
                    != shared_pressure_lease
                ):
                    raise AdmissionRuntimeConflict(
                        "operation already has a different active admission lease"
                    )
                return current.lease

            if self.shared_pressure_ledger is not None:
                shared_finder = getattr(
                    self.shared_pressure_ledger,
                    "lease_for_operation",
                    None,
                )
                if not callable(shared_finder):
                    raise AdmissionRuntimeError(
                        "shared pressure ledger does not support durable lease lookup"
                    )
                try:
                    persisted_shared = shared_finder(
                        self.shared_pressure_scope,
                        request.operation_id,
                        now=wall,
                    )
                except SharedPressureError as exc:
                    raise AdmissionRuntimeError(
                        "durable_shared_pressure_unavailable"
                    ) from exc
                if persisted_shared is None:
                    raise AdmissionRuntimeConflict(
                        "durable shared pressure lease is no longer active"
                    )
                if persisted_shared != shared_pressure_lease:
                    raise AdmissionRuntimeConflict(
                        "durable shared pressure lease does not match journal"
                    )

            try:
                recovery_state = recovery_reader(
                    request.tenant_id,
                    request.operation_id,
                )
            except QuotaError as exc:
                raise AdmissionRuntimeError(
                    "durable_recovery_state_unavailable"
                ) from exc
            if recovery_state is None:
                raise AdmissionRuntimeConflict(
                    "durable quota reservation is no longer active"
                )
            persisted, unresolved = recovery_state
            if persisted != reservation:
                raise AdmissionRuntimeConflict(
                    "durable quota reservation does not match lease"
                )

            recovered_unknown: dict[str, UnknownUsageMarker] = {}
            for event in unresolved:
                if (
                    event.reservation_id != reservation.reservation_id
                    or event.operation_id != request.operation_id
                    or not event.category.startswith(
                        _UNKNOWN_USAGE_PREFIX
                    )
                ):
                    raise AdmissionRuntimeConflict(
                        "durable unknown usage identity is invalid"
                    )
                category = event.category[len(_UNKNOWN_USAGE_PREFIX):]
                if category not in _USAGE_CATEGORIES:
                    raise AdmissionRuntimeConflict(
                        "durable unknown usage category is invalid"
                    )
                recovered_unknown[event.event_id] = UnknownUsageMarker(
                    event_id=event.event_id,
                    operation_id=request.operation_id,
                    category=category,
                    reason="durable-unknown-usage-recovered",
                    recorded_at=event.recorded_at,
                )

            self._active[request.operation_id] = _ActiveLease(
                lease=lease,
                request_fingerprint=fingerprint,
                unknown_usage=recovered_unknown,
                shared_pressure_lease=shared_pressure_lease,
            )
            self.metrics_registry.inc("admission.reattached_total")
            if recovered_unknown:
                self.metrics_registry.inc(
                    "admission.unknown_usage_reattached_total",
                    len(recovered_unknown),
                )
            return lease

    def settle_shared_pressure_recovery(
        self,
        lease: SharedPressureLease | None,
        *,
        now_wall: float | None = None,
    ) -> SharedPressureLease | None:
        """Release exact durable pressure authority during terminal recovery."""

        ledger = self.shared_pressure_ledger
        owner = self.shared_pressure_owner_id
        scope = self.shared_pressure_scope
        if lease is None:
            if ledger is None:
                return None
            raise AdmissionRuntimeError(
                "shared_pressure_recovery_metadata_missing"
            )
        if ledger is None or owner is None or scope is None:
            raise AdmissionRuntimeError(
                "shared_pressure_recovery_runtime_missing"
            )
        if (
            lease.scope != scope
            or lease.owner_id != owner
        ):
            raise AdmissionRuntimeConflict(
                "shared pressure recovery lease identity does not match runtime"
            )

        finder = getattr(ledger, "lease_for_operation", None)
        if not callable(finder):
            raise AdmissionRuntimeError(
                "shared pressure ledger does not support durable lease lookup"
            )
        try:
            persisted = finder(
                scope,
                lease.operation_id,
                now=_wall_time(now_wall, field="now_wall"),
            )
        except SharedPressureError as exc:
            raise AdmissionRuntimeError(
                "shared_pressure_recovery_lookup_failed"
            ) from exc

        if persisted is None:
            # Expiry/reaping is already a terminal release of shared capacity.
            return None
        if persisted != lease:
            raise AdmissionRuntimeConflict(
                "shared pressure recovery lease does not match durable ledger"
            )
        try:
            return ledger.release(lease.lease_id, owner)
        except SharedPressureConflict as exc:
            raise AdmissionRuntimeConflict(str(exc)) from exc
        except SharedPressureError as exc:
            raise AdmissionRuntimeError(
                "shared_pressure_recovery_release_failed"
            ) from exc

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
                if existing.category != normalized_category:
                    raise AdmissionRuntimeConflict(
                        "unknown usage event replayed with different inputs"
                    )
                if existing.reason == "durable-unknown-usage-recovered":
                    restored = UnknownUsageMarker(
                        event_id=existing.event_id,
                        operation_id=existing.operation_id,
                        category=existing.category,
                        reason=normalized_reason,
                        recorded_at=existing.recorded_at,
                    )
                    active.unknown_usage[event] = restored
                    return restored
                if existing.reason != normalized_reason:
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

            effective_actual = _effective_actual_usage(
                actual,
                quota_completion,
            )
            operation_overruns = _operation_budget_overruns(
                active.lease.decision,
                effective_actual,
            )

            if active.shared_pressure_lease is not None:
                self._release_shared_pressure(
                    active.shared_pressure_lease
                )
            self.metrics_registry.inc("admission.completed_total")
            if operation_overruns:
                self.metrics_registry.inc(
                    "admission.operation_overrun_total"
                )
                for dimension in operation_overruns:
                    self.metrics_registry.inc(
                        "admission.operation_overrun."
                        + dimension
                        + "_total"
                    )
            _observe_usage(
                self.metrics_registry,
                "actual",
                effective_actual,
            )
            _observe_usage_delta(
                self.metrics_registry,
                active.lease.decision.estimated,
                effective_actual,
            )
            self._active.pop(operation)
            return AdmissionCompletion(
                lease=active.lease,
                quota_completion=quota_completion,
                completed_at=wall,
                effective_actual=effective_actual,
                operation_overrun_dimensions=operation_overruns,
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
    "admission_lease_id",
]
