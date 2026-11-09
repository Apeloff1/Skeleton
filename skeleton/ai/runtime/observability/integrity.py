"""Observability integrity monitor for hostile gap G023.

Telemetry must be allowed to fail without taking the product down, but the
system must not confuse missing telemetry with healthy telemetry. This module
monitors the monitors through source heartbeats, loss/gap accounting,
cardinality budgets, and trace completeness.

The monitor stores identifiers, counters, and digests only. It never becomes
canonical product state and cannot make application correctness depend on a
telemetry backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import hashlib
import json
import math
import re
import threading
from typing import Any, Iterable

from skeleton.observability.resilient_telemetry import ResilientTelemetry


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ObservabilityIntegrityError(RuntimeError):
    """Invalid integrity evidence or monitor configuration."""


class ObservabilityIntegrityConflict(ObservabilityIntegrityError):
    """An observation replays a stable identity with different evidence."""


class IntegrityStatus(IntEnum):
    HEALTHY = 0
    DEGRADED = 1
    BREACHED = 2
    UNKNOWN = 3


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ObservabilityIntegrityError(
            f"{field} must be canonical non-empty text"
        )
    if len(value) > maximum:
        raise ObservabilityIntegrityError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ObservabilityIntegrityError(f"{field} contains control characters")
    return value


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = 1_000_000_000_000,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise ObservabilityIntegrityError(
            f"{field} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _fraction(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ObservabilityIntegrityError(f"{field} must be in [0, 1]")
    return float(value)


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ObservabilityIntegrityError(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class TelemetrySourcePolicy:
    source: str
    heartbeat_timeout_ticks: int = 8
    max_loss_fraction: float = 0.01
    max_sequence_gap: int = 0
    cardinality_budget: int = 1024
    critical: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(
            self,
            "heartbeat_timeout_ticks",
            _integer(
                self.heartbeat_timeout_ticks,
                "heartbeat_timeout_ticks",
                minimum=1,
                maximum=1_000_000,
            ),
        )
        object.__setattr__(
            self,
            "max_loss_fraction",
            _fraction(self.max_loss_fraction, "max_loss_fraction"),
        )
        object.__setattr__(
            self,
            "max_sequence_gap",
            _integer(self.max_sequence_gap, "max_sequence_gap"),
        )
        object.__setattr__(
            self,
            "cardinality_budget",
            _integer(self.cardinality_budget, "cardinality_budget", minimum=1),
        )


@dataclass(frozen=True, slots=True)
class TelemetryReceiptObservation:
    source: str
    sequence: int
    event_digest: str
    series_id: str
    delivered: bool
    critical: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(
            self, "sequence", _integer(self.sequence, "sequence", minimum=1)
        )
        object.__setattr__(
            self, "event_digest", _digest(self.event_digest, "event_digest")
        )
        object.__setattr__(self, "series_id", _digest(self.series_id, "series_id"))
        if not isinstance(self.delivered, bool) or not isinstance(self.critical, bool):
            raise ObservabilityIntegrityError(
                "delivered and critical must be boolean"
            )

    @property
    def identity_digest(self) -> str:
        return _canonical_digest(
            {
                "source": self.source,
                "sequence": self.sequence,
                "event_digest": self.event_digest,
                "series_id": self.series_id,
                "delivered": self.delivered,
                "critical": self.critical,
            }
        )


@dataclass(frozen=True, slots=True)
class TraceExpectation:
    trace_id: str
    required_stages: tuple[str, ...]
    deadline_tick: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _text(self.trace_id, "trace_id"))
        stages = tuple(
            sorted({_text(stage, "trace_stage") for stage in self.required_stages})
        )
        if not stages:
            raise ObservabilityIntegrityError("trace requires at least one stage")
        object.__setattr__(self, "required_stages", stages)
        object.__setattr__(
            self,
            "deadline_tick",
            _integer(self.deadline_tick, "deadline_tick", minimum=1),
        )


@dataclass(frozen=True, slots=True)
class SourceIntegrity:
    source: str
    status: IntegrityStatus
    emitted: int
    delivered: int
    lost: int
    loss_fraction: float
    sequence_gap_total: int
    last_sequence: int
    last_heartbeat_tick: int | None
    series_count: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status.name.lower(),
            "emitted": self.emitted,
            "delivered": self.delivered,
            "lost": self.lost,
            "loss_fraction": self.loss_fraction,
            "sequence_gap_total": self.sequence_gap_total,
            "last_sequence": self.last_sequence,
            "last_heartbeat_tick": self.last_heartbeat_tick,
            "series_count": self.series_count,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    status: IntegrityStatus
    tick: int
    sources: tuple[SourceIntegrity, ...]
    incomplete_traces: tuple[str, ...]
    report_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.observability_integrity_report.v1",
            "status": self.status.name.lower(),
            "tick": self.tick,
            "sources": [source.as_dict() for source in self.sources],
            "incomplete_traces": list(self.incomplete_traces),
            "report_digest": self.report_digest,
            "canonical_state_dependency": False,
            "completion_checkbox": False,
            "verification_signature": False,
        }


@dataclass(slots=True)
class _SourceState:
    last_sequence: int = 0
    emitted: int = 0
    delivered: int = 0
    lost: int = 0
    gap_total: int = 0
    last_heartbeat_tick: int | None = None
    series: set[str] = field(default_factory=set)
    observations: dict[int, str] = field(default_factory=dict)


class ObservabilityIntegrityMonitor:
    """Monitor telemetry freshness, loss, cardinality, and trace completeness."""

    def __init__(self, policies: Iterable[TelemetrySourcePolicy]) -> None:
        policies = tuple(policies)
        if not policies:
            raise ObservabilityIntegrityError(
                "at least one source policy is required"
            )
        if any(
            not isinstance(policy, TelemetrySourcePolicy)
            for policy in policies
        ):
            raise TypeError("policies must contain TelemetrySourcePolicy")
        if len({policy.source for policy in policies}) != len(policies):
            raise ObservabilityIntegrityError(
                "duplicate telemetry source policy"
            )
        self._policies = {policy.source: policy for policy in policies}
        self._state = {source: _SourceState() for source in self._policies}
        self._traces: dict[str, TraceExpectation] = {}
        self._trace_stages: dict[str, set[str]] = {}
        self._tick = 0
        self._lock = threading.RLock()

    @property
    def tick(self) -> int:
        with self._lock:
            return self._tick

    def advance(self, steps: int = 1) -> int:
        count = _integer(steps, "steps", minimum=1, maximum=1_000_000)
        with self._lock:
            self._tick += count
            return self._tick

    def heartbeat(self, source: str) -> int:
        canonical = self._policy(source).source
        with self._lock:
            self._tick += 1
            self._state[canonical].last_heartbeat_tick = self._tick
            return self._tick

    def observe(self, observation: TelemetryReceiptObservation) -> None:
        if not isinstance(observation, TelemetryReceiptObservation):
            raise TypeError("observation must be TelemetryReceiptObservation")
        policy = self._policy(observation.source)
        with self._lock:
            state = self._state[policy.source]
            prior_identity = state.observations.get(observation.sequence)
            if prior_identity is not None:
                if prior_identity != observation.identity_digest:
                    raise ObservabilityIntegrityConflict(
                        "telemetry sequence replay changed identity"
                    )
                return
            if observation.sequence <= state.last_sequence:
                raise ObservabilityIntegrityConflict(
                    "telemetry sequence regressed"
                )
            if state.last_sequence:
                gap = observation.sequence - state.last_sequence - 1
                if gap > 0:
                    state.gap_total += gap
                    state.emitted += gap
                    state.lost += gap
            state.last_sequence = observation.sequence
            state.emitted += 1
            if observation.delivered:
                state.delivered += 1
            else:
                state.lost += 1
            state.series.add(observation.series_id)
            state.observations[observation.sequence] = observation.identity_digest
            if observation.critical and not observation.delivered:
                state.gap_total += 1
            self._tick += 1
            state.last_heartbeat_tick = self._tick

    def audit_resilient_telemetry(
        self,
        source: str,
        telemetry: ResilientTelemetry,
    ) -> None:
        """Import bounded reconstruction receipts and delivery totals."""

        canonical = self._policy(source).source
        if not isinstance(telemetry, ResilientTelemetry):
            raise TypeError("telemetry must be ResilientTelemetry")
        receipts = telemetry.receipts()
        reconstruction = telemetry.reconstruct()
        delivered_total = int(reconstruction["delivered_total"])
        sink_failures = int(reconstruction["sink_failures_total"])
        with self._lock:
            state = self._state[canonical]
            for receipt in receipts:
                prior = state.observations.get(receipt.sequence)
                identity = _canonical_digest(
                    {
                        "source": canonical,
                        "sequence": receipt.sequence,
                        "event_digest": receipt.event_digest,
                        "series_id": receipt.series_id,
                    }
                )
                if prior is not None and prior != identity:
                    raise ObservabilityIntegrityConflict(
                        "resilient telemetry receipt identity changed"
                    )
                if prior is None:
                    if (
                        state.last_sequence
                        and receipt.sequence > state.last_sequence + 1
                    ):
                        state.gap_total += (
                            receipt.sequence - state.last_sequence - 1
                        )
                    state.last_sequence = max(
                        state.last_sequence, receipt.sequence
                    )
                    state.series.add(receipt.series_id)
                    state.observations[receipt.sequence] = identity
            emitted_total = delivered_total + sink_failures
            state.emitted = max(state.emitted, emitted_total)
            state.delivered = max(state.delivered, delivered_total)
            state.lost = max(state.lost, sink_failures)
            self._tick += 1
            state.last_heartbeat_tick = self._tick

    def expect_trace(
        self,
        trace_id: str,
        required_stages: Iterable[str],
        *,
        deadline_after_ticks: int,
    ) -> TraceExpectation:
        trace = _text(trace_id, "trace_id")
        delay = _integer(
            deadline_after_ticks,
            "deadline_after_ticks",
            minimum=1,
            maximum=1_000_000,
        )
        stages = tuple(required_stages)
        with self._lock:
            expectation = TraceExpectation(
                trace_id=trace,
                required_stages=stages,
                deadline_tick=self._tick + delay,
            )
            prior = self._traces.get(trace)
            if prior is not None and prior != expectation:
                raise ObservabilityIntegrityConflict(
                    "trace expectation replay changed identity"
                )
            self._traces[trace] = expectation
            self._trace_stages.setdefault(trace, set())
            return expectation

    def observe_trace_stage(self, trace_id: str, stage: str) -> None:
        trace = _text(trace_id, "trace_id")
        canonical_stage = _text(stage, "trace_stage")
        with self._lock:
            expectation = self._traces.get(trace)
            if expectation is None:
                raise ObservabilityIntegrityError(
                    "unknown trace expectation"
                )
            if canonical_stage not in expectation.required_stages:
                raise ObservabilityIntegrityError(
                    "trace stage is not declared"
                )
            self._trace_stages[trace].add(canonical_stage)
            self._tick += 1

    def report(self) -> IntegrityReport:
        with self._lock:
            sources = tuple(
                self._source_integrity(policy)
                for policy in sorted(
                    self._policies.values(),
                    key=lambda value: value.source,
                )
            )
            incomplete = tuple(
                sorted(
                    trace_id
                    for trace_id, expectation in self._traces.items()
                    if self._tick >= expectation.deadline_tick
                    and not set(expectation.required_stages).issubset(
                        self._trace_stages.get(trace_id, set())
                    )
                )
            )
            statuses = [source.status for source in sources]
            if incomplete:
                statuses.append(IntegrityStatus.DEGRADED)
            overall = max(statuses, default=IntegrityStatus.UNKNOWN)
            payload = {
                "tick": self._tick,
                "sources": [source.as_dict() for source in sources],
                "incomplete_traces": list(incomplete),
            }
            return IntegrityReport(
                status=overall,
                tick=self._tick,
                sources=sources,
                incomplete_traces=incomplete,
                report_digest=_canonical_digest(payload),
            )

    def _source_integrity(
        self,
        policy: TelemetrySourcePolicy,
    ) -> SourceIntegrity:
        state = self._state[policy.source]
        reasons: list[str] = []
        status = IntegrityStatus.HEALTHY
        if (
            state.last_heartbeat_tick is None
            or self._tick - state.last_heartbeat_tick
            > policy.heartbeat_timeout_ticks
        ):
            status = IntegrityStatus.UNKNOWN
            reasons.append("heartbeat-stale-or-missing")
        loss_fraction = (
            state.lost / state.emitted if state.emitted else 0.0
        )
        if loss_fraction > policy.max_loss_fraction:
            status = max(status, IntegrityStatus.BREACHED)
            reasons.append("loss-budget-exceeded")
        if state.gap_total > policy.max_sequence_gap:
            status = max(status, IntegrityStatus.BREACHED)
            reasons.append("sequence-gap-budget-exceeded")
        if len(state.series) > policy.cardinality_budget:
            status = max(status, IntegrityStatus.DEGRADED)
            reasons.append("cardinality-budget-exceeded")
        if policy.critical and state.emitted == 0:
            status = IntegrityStatus.UNKNOWN
            reasons.append("critical-source-has-no-evidence")
        return SourceIntegrity(
            source=policy.source,
            status=status,
            emitted=state.emitted,
            delivered=state.delivered,
            lost=state.lost,
            loss_fraction=loss_fraction,
            sequence_gap_total=state.gap_total,
            last_sequence=state.last_sequence,
            last_heartbeat_tick=state.last_heartbeat_tick,
            series_count=len(state.series),
            reasons=tuple(reasons),
        )

    def _policy(self, source: str) -> TelemetrySourcePolicy:
        canonical = _text(source, "source")
        try:
            return self._policies[canonical]
        except KeyError as exc:
            raise ObservabilityIntegrityError(
                f"unknown telemetry source: {canonical}"
            ) from exc


__all__ = [
    "IntegrityReport",
    "IntegrityStatus",
    "ObservabilityIntegrityConflict",
    "ObservabilityIntegrityError",
    "ObservabilityIntegrityMonitor",
    "SourceIntegrity",
    "TelemetryReceiptObservation",
    "TelemetrySourcePolicy",
    "TraceExpectation",
]
