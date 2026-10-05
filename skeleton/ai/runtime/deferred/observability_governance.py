"""Deterministic observability, reliability-budget, cost, and efficiency contracts.

This module implements the executable core for VOL-180 through VOL-187.  The
contracts are intentionally side-effect free: they evaluate evidence and return
decisions, but do not deploy, release, spend, or mutate production authority.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
from typing import Iterable, Sequence


PPM = 1_000_000
HEX = frozenset("0123456789abcdef")


class ObservabilityGovernanceError(ValueError):
    """An observability-governance invariant failed closed."""


def _token(name: str, value: object, *, limit: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > limit
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ObservabilityGovernanceError(
            f"{name} must be non-empty normalized text"
        )
    return value


def _tokens(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ObservabilityGovernanceError(f"{name} must be a collection")
    return tuple(sorted({_token(name, value) for value in values}))


def _integer(name: str, value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ObservabilityGovernanceError(
            f"{name} must be an integer >= {minimum}"
        )
    return value


def _ppm(name: str, value: object, *, allow_zero: bool = True) -> int:
    minimum = 0 if allow_zero else 1
    result = _integer(name, value, minimum=minimum)
    if result > PPM:
        raise ObservabilityGovernanceError(f"{name} must be <= {PPM}")
    return result


def _hex(name: str, value: object, length: int) -> str:
    token = _token(name, value, limit=length)
    lowered = token.lower()
    if len(lowered) != length or any(ch not in HEX for ch in lowered):
        raise ObservabilityGovernanceError(
            f"{name} must be {length} lowercase hexadecimal characters"
        )
    return lowered


def _digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ObservabilityGovernanceError(
            "evidence payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _ratio_ppm(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ObservabilityGovernanceError("ratio denominator must be positive")
    return min(PPM, max(0, (numerator * PPM) // denominator))


# ---------------------------------------------------------------------------
# VOL-180: Service Level Objectives
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SLI:
    sli_id: str
    good_event_name: str
    total_event_name: str
    unit: str = "events"

    def __post_init__(self) -> None:
        for name in ("sli_id", "good_event_name", "total_event_name", "unit"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "sli_id": self.sli_id,
                "good_event_name": self.good_event_name,
                "total_event_name": self.total_event_name,
                "unit": self.unit,
            }
        )


@dataclass(frozen=True, slots=True)
class SLO:
    slo_id: str
    service: str
    operation_class: str
    sli_id: str
    target_ppm: int
    window_ms: int
    min_total_events: int
    excluded_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("slo_id", "service", "operation_class", "sli_id"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(
            self, "target_ppm", _ppm("target_ppm", self.target_ppm, allow_zero=False)
        )
        object.__setattr__(self, "window_ms", _integer("window_ms", self.window_ms, minimum=1))
        object.__setattr__(
            self,
            "min_total_events",
            _integer("min_total_events", self.min_total_events, minimum=1),
        )
        object.__setattr__(
            self,
            "excluded_conditions",
            _tokens("excluded_condition", self.excluded_conditions),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "slo_id": self.slo_id,
                "service": self.service,
                "operation_class": self.operation_class,
                "sli_id": self.sli_id,
                "target_ppm": self.target_ppm,
                "window_ms": self.window_ms,
                "min_total_events": self.min_total_events,
                "excluded_conditions": list(self.excluded_conditions),
            }
        )


@dataclass(frozen=True, slots=True)
class SLOWindow:
    window_id: str
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _token("window_id", self.window_id))
        object.__setattr__(self, "start_ms", _integer("start_ms", self.start_ms))
        object.__setattr__(self, "end_ms", _integer("end_ms", self.end_ms, minimum=1))
        if self.end_ms <= self.start_ms:
            raise ObservabilityGovernanceError("SLO window must have positive duration")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class SLIObservation:
    observation_id: str
    sli_id: str
    timestamp_ms: int
    good_events: int
    total_events: int
    excluded_condition: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observation_id", _token("observation_id", self.observation_id)
        )
        object.__setattr__(self, "sli_id", _token("sli_id", self.sli_id))
        object.__setattr__(
            self, "timestamp_ms", _integer("timestamp_ms", self.timestamp_ms)
        )
        object.__setattr__(
            self, "good_events", _integer("good_events", self.good_events)
        )
        object.__setattr__(
            self, "total_events", _integer("total_events", self.total_events)
        )
        if self.good_events > self.total_events:
            raise ObservabilityGovernanceError(
                "good_events cannot exceed total_events"
            )
        if self.excluded_condition is not None:
            object.__setattr__(
                self,
                "excluded_condition",
                _token("excluded_condition", self.excluded_condition),
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "observation_id": self.observation_id,
                "sli_id": self.sli_id,
                "timestamp_ms": self.timestamp_ms,
                "good_events": self.good_events,
                "total_events": self.total_events,
                "excluded_condition": self.excluded_condition,
            }
        )


@dataclass(frozen=True, slots=True)
class SLOResult:
    slo_digest: str
    window_id: str
    total_events: int
    good_events: int
    excluded_events: int
    achieved_ppm: int
    eligible: bool
    met: bool
    reason_code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "slo_digest", _hex("slo_digest", self.slo_digest, 64))
        object.__setattr__(self, "window_id", _token("window_id", self.window_id))
        for name in ("total_events", "good_events", "excluded_events"):
            object.__setattr__(
                self, name, _integer(name, getattr(self, name))
            )
        object.__setattr__(self, "achieved_ppm", _ppm("achieved_ppm", self.achieved_ppm))
        if not isinstance(self.eligible, bool) or not isinstance(self.met, bool):
            raise ObservabilityGovernanceError("SLO booleans must be explicit")
        if self.met and not self.eligible:
            raise ObservabilityGovernanceError("ineligible SLO result cannot be green")
        object.__setattr__(self, "reason_code", _token("reason_code", self.reason_code))

    @property
    def bad_events(self) -> int:
        return max(0, self.total_events - self.good_events)


def evaluate_slo(
    slo: SLO,
    window: SLOWindow,
    observations: Sequence[SLIObservation],
) -> SLOResult:
    """Evaluate authoritative SLI evidence for one declared SLO window."""
    if window.duration_ms != slo.window_ms:
        raise ObservabilityGovernanceError(
            "SLO window duration must exactly match declared window_ms"
        )
    total = 0
    good = 0
    excluded = 0
    allowed_exclusions = set(slo.excluded_conditions)
    seen: set[str] = set()
    for observation in sorted(observations, key=lambda item: (item.timestamp_ms, item.observation_id)):
        if observation.observation_id in seen:
            raise ObservabilityGovernanceError("duplicate SLI observation identity")
        seen.add(observation.observation_id)
        if observation.sli_id != slo.sli_id:
            raise ObservabilityGovernanceError("SLI observation bound to wrong SLI")
        if not (window.start_ms <= observation.timestamp_ms < window.end_ms):
            continue
        if observation.excluded_condition is not None:
            if observation.excluded_condition not in allowed_exclusions:
                raise ObservabilityGovernanceError(
                    "undeclared SLO exclusion fails closed"
                )
            excluded += observation.total_events
            continue
        total += observation.total_events
        good += observation.good_events

    if total < slo.min_total_events:
        achieved = _ratio_ppm(good, total) if total else 0
        return SLOResult(
            slo.digest,
            window.window_id,
            total,
            good,
            excluded,
            achieved,
            False,
            False,
            "insufficient_authoritative_volume",
        )
    achieved = _ratio_ppm(good, total)
    met = achieved >= slo.target_ppm
    return SLOResult(
        slo.digest,
        window.window_id,
        total,
        good,
        excluded,
        achieved,
        True,
        met,
        "target_met" if met else "target_missed",
    )


# ---------------------------------------------------------------------------
# VOL-181: Error budgets and burn-rate release policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ErrorBudget:
    budget_id: str
    slo_id: str
    allowed_bad_ppm: int
    warn_burn_rate_milli: int = 1_000
    freeze_burn_rate_milli: int = 2_000

    def __post_init__(self) -> None:
        object.__setattr__(self, "budget_id", _token("budget_id", self.budget_id))
        object.__setattr__(self, "slo_id", _token("slo_id", self.slo_id))
        object.__setattr__(
            self, "allowed_bad_ppm", _ppm("allowed_bad_ppm", self.allowed_bad_ppm)
        )
        object.__setattr__(
            self,
            "warn_burn_rate_milli",
            _integer("warn_burn_rate_milli", self.warn_burn_rate_milli, minimum=1),
        )
        object.__setattr__(
            self,
            "freeze_burn_rate_milli",
            _integer("freeze_burn_rate_milli", self.freeze_burn_rate_milli, minimum=1),
        )
        if self.freeze_burn_rate_milli < self.warn_burn_rate_milli:
            raise ObservabilityGovernanceError(
                "freeze burn threshold must be >= warning threshold"
            )


@dataclass(frozen=True, slots=True)
class BurnRate:
    consumed_bad_events: int
    expected_bad_events: int
    rate_milli: int

    def __post_init__(self) -> None:
        for name in ("consumed_bad_events", "expected_bad_events", "rate_milli"):
            object.__setattr__(self, name, _integer(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    budget_id: str
    status: str
    release_allowed: bool
    reason_code: str
    burn_rate: BurnRate
    safety_gates_bypassable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "budget_id", _token("budget_id", self.budget_id))
        if self.status not in {"healthy", "warn", "freeze"}:
            raise ObservabilityGovernanceError("unknown error-budget status")
        if not isinstance(self.release_allowed, bool):
            raise ObservabilityGovernanceError("release_allowed must be boolean")
        if self.status == "freeze" and self.release_allowed:
            raise ObservabilityGovernanceError("frozen budget cannot allow release")
        if self.safety_gates_bypassable is not False:
            raise ObservabilityGovernanceError(
                "error budgets may not bypass safety or reliability gates"
            )
        object.__setattr__(self, "reason_code", _token("reason_code", self.reason_code))


def error_budget_for_slo(slo: SLO, *, budget_id: str | None = None) -> ErrorBudget:
    return ErrorBudget(
        budget_id=budget_id or f"budget:{slo.slo_id}",
        slo_id=slo.slo_id,
        allowed_bad_ppm=PPM - slo.target_ppm,
    )


def evaluate_error_budget(
    budget: ErrorBudget,
    slo: SLO,
    result: SLOResult,
) -> BudgetDecision:
    if budget.slo_id != slo.slo_id:
        raise ObservabilityGovernanceError("error budget bound to wrong SLO")
    if result.slo_digest != slo.digest:
        raise ObservabilityGovernanceError("SLO result identity mismatch")
    if not result.eligible:
        burn = BurnRate(result.bad_events, 0, budget.freeze_burn_rate_milli)
        return BudgetDecision(
            budget.budget_id,
            "freeze",
            False,
            "insufficient_authoritative_sli_evidence",
            burn,
        )

    consumed = result.bad_events
    if budget.allowed_bad_ppm == 0:
        rate = 0 if consumed == 0 else budget.freeze_burn_rate_milli
        expected = 0
    else:
        expected = max(
            1,
            (result.total_events * budget.allowed_bad_ppm + PPM - 1) // PPM,
        )
        rate = (consumed * 1_000) // expected

    burn = BurnRate(consumed, expected, rate)
    if rate >= budget.freeze_burn_rate_milli:
        return BudgetDecision(
            budget.budget_id, "freeze", False, "error_budget_exhausting", burn
        )
    if rate >= budget.warn_burn_rate_milli:
        return BudgetDecision(
            budget.budget_id, "warn", True, "error_budget_burning_fast", burn
        )
    return BudgetDecision(
        budget.budget_id, "healthy", True, "error_budget_healthy", burn
    )


# ---------------------------------------------------------------------------
# VOL-182: Observability cardinality and sampling controls
# ---------------------------------------------------------------------------


_FORBIDDEN_LABEL_TOKENS = (
    "secret",
    "token",
    "password",
    "prompt",
    "content",
    "email",
    "authorization",
    "cookie",
)


@dataclass(frozen=True, slots=True)
class TelemetryLabel:
    key: str
    value: str
    classification: str = "bounded"

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _token("label key", self.key, limit=96))
        object.__setattr__(self, "value", _token("label value", self.value, limit=192))
        if self.classification not in {
            "bounded",
            "high-cardinality",
            "sensitive",
            "user-content",
            "secret",
        }:
            raise ObservabilityGovernanceError("unknown telemetry label classification")
        lowered = self.key.lower()
        if any(token in lowered for token in _FORBIDDEN_LABEL_TOKENS):
            raise ObservabilityGovernanceError(
                "sensitive or user-content telemetry label key is forbidden"
            )
        if self.classification in {"sensitive", "user-content", "secret"}:
            raise ObservabilityGovernanceError(
                "sensitive or user-content telemetry dimensions are forbidden"
            )


@dataclass(frozen=True, slots=True)
class TelemetrySeries:
    metric_name: str
    labels: tuple[TelemetryLabel, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "metric_name", _token("metric_name", self.metric_name, limit=160)
        )
        labels = tuple(sorted(self.labels, key=lambda item: item.key))
        keys = [label.key for label in labels]
        if len(keys) != len(set(keys)):
            raise ObservabilityGovernanceError("telemetry label keys must be unique")
        object.__setattr__(self, "labels", labels)

    @property
    def identity(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return (
            self.metric_name,
            tuple((label.key, label.value) for label in self.labels),
        )


@dataclass(frozen=True, slots=True)
class CardinalityBudget:
    metric_name: str
    allowed_label_keys: tuple[str, ...]
    high_cardinality_exceptions: tuple[str, ...] = ()
    max_series: int = 1_000
    max_values_per_label: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "metric_name", _token("metric_name", self.metric_name, limit=160)
        )
        allowed = _tokens("allowed_label_key", self.allowed_label_keys)
        if not allowed:
            raise ObservabilityGovernanceError(
                "cardinality budget requires declared label keys"
            )
        object.__setattr__(self, "allowed_label_keys", allowed)
        exceptions = _tokens(
            "high_cardinality_exception", self.high_cardinality_exceptions
        )
        if not set(exceptions).issubset(set(allowed)):
            raise ObservabilityGovernanceError(
                "high-cardinality exception must be an allowed label"
            )
        object.__setattr__(self, "high_cardinality_exceptions", exceptions)
        object.__setattr__(
            self, "max_series", _integer("max_series", self.max_series, minimum=1)
        )
        object.__setattr__(
            self,
            "max_values_per_label",
            _integer(
                "max_values_per_label", self.max_values_per_label, minimum=1
            ),
        )


@dataclass(frozen=True, slots=True)
class SamplingPolicy:
    policy_id: str
    sample_rate_ppm: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _token("policy_id", self.policy_id))
        object.__setattr__(
            self,
            "sample_rate_ppm",
            _ppm("sample_rate_ppm", self.sample_rate_ppm),
        )

    def includes(self, stable_identity: str) -> bool:
        identity = _token("stable_identity", stable_identity, limit=512)
        bucket = int(hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16], 16) % PPM
        return bucket < self.sample_rate_ppm


@dataclass(frozen=True, slots=True)
class CardinalityDecision:
    allowed: bool
    reason_code: str
    projected_series: int

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise ObservabilityGovernanceError("allowed must be boolean")
        object.__setattr__(self, "reason_code", _token("reason_code", self.reason_code))
        object.__setattr__(
            self,
            "projected_series",
            _integer("projected_series", self.projected_series),
        )


def evaluate_cardinality(
    budget: CardinalityBudget,
    existing: Sequence[TelemetrySeries],
    candidate: TelemetrySeries,
) -> CardinalityDecision:
    if candidate.metric_name != budget.metric_name:
        raise ObservabilityGovernanceError("candidate metric does not match budget")
    allowed_keys = set(budget.allowed_label_keys)
    exceptions = set(budget.high_cardinality_exceptions)
    for label in candidate.labels:
        if label.key not in allowed_keys:
            return CardinalityDecision(False, "undeclared_label_key", len(existing))
        if label.classification == "high-cardinality" and label.key not in exceptions:
            return CardinalityDecision(
                False, "high_cardinality_without_exception", len(existing)
            )

    identities = {
        series.identity
        for series in existing
        if series.metric_name == budget.metric_name
    }
    projected = len(identities | {candidate.identity})
    if projected > budget.max_series:
        return CardinalityDecision(False, "series_budget_exceeded", projected)

    value_sets: dict[str, set[str]] = {key: set() for key in allowed_keys}
    for series in tuple(existing) + (candidate,):
        if series.metric_name != budget.metric_name:
            continue
        for label in series.labels:
            if label.key in value_sets:
                value_sets[label.key].add(label.value)
    for key, values in value_sets.items():
        if len(values) > budget.max_values_per_label and key not in exceptions:
            return CardinalityDecision(False, f"label_value_budget_exceeded:{key}", projected)
    return CardinalityDecision(True, "within_cardinality_budget", projected)


# ---------------------------------------------------------------------------
# VOL-183: Stable trace and causal-link model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TraceId:
    trace_id: str
    correlation_id: str
    operation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _hex("trace_id", self.trace_id, 32))
        object.__setattr__(
            self, "correlation_id", _token("correlation_id", self.correlation_id)
        )
        object.__setattr__(
            self, "operation_id", _token("operation_id", self.operation_id)
        )


@dataclass(frozen=True, slots=True)
class TraceLink:
    trace_id: str
    span_id: str
    relation: str = "causal"

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _hex("trace_id", self.trace_id, 32))
        object.__setattr__(self, "span_id", _hex("span_id", self.span_id, 16))
        object.__setattr__(self, "relation", _token("relation", self.relation))


@dataclass(frozen=True, slots=True)
class Span:
    identity: TraceId
    span_id: str
    name: str
    parent_span_id: str | None = None
    links: tuple[TraceLink, ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()
    authoritative_state: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "span_id", _hex("span_id", self.span_id, 16))
        object.__setattr__(self, "name", _token("span name", self.name))
        if self.parent_span_id is not None:
            object.__setattr__(
                self,
                "parent_span_id",
                _hex("parent_span_id", self.parent_span_id, 16),
            )
            if self.parent_span_id == self.span_id:
                raise ObservabilityGovernanceError("span cannot parent itself")
        links = tuple(sorted(self.links, key=lambda item: (item.trace_id, item.span_id, item.relation)))
        object.__setattr__(self, "links", links)
        attrs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for key, value in self.attributes:
            normalized_key = _token("trace attribute key", key, limit=96)
            lowered = normalized_key.lower()
            if any(token in lowered for token in _FORBIDDEN_LABEL_TOKENS):
                raise ObservabilityGovernanceError(
                    "sensitive trace attribute key is forbidden"
                )
            if normalized_key in seen:
                raise ObservabilityGovernanceError("duplicate trace attribute key")
            seen.add(normalized_key)
            attrs.append(
                (
                    normalized_key,
                    _token("trace attribute value", value, limit=256),
                )
            )
        object.__setattr__(self, "attributes", tuple(sorted(attrs)))
        if self.authoritative_state is not False:
            raise ObservabilityGovernanceError(
                "telemetry spans cannot be authoritative application state"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "trace_id": self.identity.trace_id,
                "correlation_id": self.identity.correlation_id,
                "operation_id": self.identity.operation_id,
                "span_id": self.span_id,
                "name": self.name,
                "parent_span_id": self.parent_span_id,
                "links": [
                    {
                        "trace_id": link.trace_id,
                        "span_id": link.span_id,
                        "relation": link.relation,
                    }
                    for link in self.links
                ],
                "attributes": list(self.attributes),
                "authoritative_state": False,
            }
        )


@dataclass(frozen=True, slots=True)
class TraceGraph:
    spans: tuple[Span, ...]

    def __post_init__(self) -> None:
        spans = tuple(sorted(self.spans, key=lambda item: item.span_id))
        if not spans:
            raise ObservabilityGovernanceError("trace graph requires at least one span")
        span_ids = [span.span_id for span in spans]
        if len(span_ids) != len(set(span_ids)):
            raise ObservabilityGovernanceError("duplicate span identity")
        identities = {
            (
                span.identity.trace_id,
                span.identity.correlation_id,
                span.identity.operation_id,
            )
            for span in spans
        }
        if len(identities) != 1:
            raise ObservabilityGovernanceError(
                "trace graph lost stable trace/correlation/operation identity"
            )
        known = set(span_ids)
        roots = 0
        parent_of: dict[str, str] = {}
        for span in spans:
            if span.parent_span_id is None:
                roots += 1
            else:
                if span.parent_span_id not in known:
                    raise ObservabilityGovernanceError(
                        "span parent missing from trace graph"
                    )
                parent_of[span.span_id] = span.parent_span_id
        if roots != 1:
            raise ObservabilityGovernanceError(
                "trace graph must contain exactly one local root"
            )
        for start in parent_of:
            visited: set[str] = set()
            cursor = start
            while cursor in parent_of:
                if cursor in visited:
                    raise ObservabilityGovernanceError("trace parent cycle detected")
                visited.add(cursor)
                cursor = parent_of[cursor]
        object.__setattr__(self, "spans", spans)

    @property
    def digest(self) -> str:
        return _digest([span.digest for span in self.spans])


# ---------------------------------------------------------------------------
# VOL-184: Reproducible performance profiling
# ---------------------------------------------------------------------------


_PROFILE_PHASES = frozenset({"startup", "steady", "tail"})


@dataclass(frozen=True, slots=True)
class ProfileSample:
    phase: str
    stage: str
    wall_ns: int
    cpu_ns: int
    allocated_bytes: int = 0

    def __post_init__(self) -> None:
        if self.phase not in _PROFILE_PHASES:
            raise ObservabilityGovernanceError("unknown profile phase")
        object.__setattr__(self, "stage", _token("profile stage", self.stage))
        object.__setattr__(self, "wall_ns", _integer("wall_ns", self.wall_ns, minimum=1))
        object.__setattr__(self, "cpu_ns", _integer("cpu_ns", self.cpu_ns))
        object.__setattr__(
            self,
            "allocated_bytes",
            _integer("allocated_bytes", self.allocated_bytes),
        )


@dataclass(frozen=True, slots=True)
class ProfileRun:
    run_id: str
    workload_id: str
    environment_id: str
    revision: str
    samples: tuple[ProfileSample, ...]

    def __post_init__(self) -> None:
        for name in ("run_id", "workload_id", "environment_id"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(self, "revision", _hex("revision", self.revision, 40))
        if not self.samples:
            raise ObservabilityGovernanceError("profile run requires samples")
        object.__setattr__(
            self,
            "samples",
            tuple(
                sorted(
                    self.samples,
                    key=lambda item: (
                        item.phase,
                        item.stage,
                        item.wall_ns,
                        item.cpu_ns,
                        item.allocated_bytes,
                    ),
                )
            ),
        )

    def wall_ns_for(self, phase: str) -> int:
        if phase not in _PROFILE_PHASES:
            raise ObservabilityGovernanceError("unknown profile phase")
        return sum(sample.wall_ns for sample in self.samples if sample.phase == phase)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "run_id": self.run_id,
                "workload_id": self.workload_id,
                "environment_id": self.environment_id,
                "revision": self.revision,
                "samples": [
                    {
                        "phase": sample.phase,
                        "stage": sample.stage,
                        "wall_ns": sample.wall_ns,
                        "cpu_ns": sample.cpu_ns,
                        "allocated_bytes": sample.allocated_bytes,
                    }
                    for sample in self.samples
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class PerformanceFinding:
    phase: str
    baseline_wall_ns: int
    candidate_wall_ns: int
    regression_ppm: int

    def __post_init__(self) -> None:
        if self.phase not in _PROFILE_PHASES:
            raise ObservabilityGovernanceError("unknown finding phase")
        for name in ("baseline_wall_ns", "candidate_wall_ns", "regression_ppm"):
            object.__setattr__(
                self, name, _integer(name, getattr(self, name))
            )


def compare_profiles(
    baseline: ProfileRun,
    candidate: ProfileRun,
    *,
    regression_threshold_ppm: int = 50_000,
) -> tuple[PerformanceFinding, ...]:
    threshold = _ppm("regression_threshold_ppm", regression_threshold_ppm)
    if baseline.workload_id != candidate.workload_id:
        raise ObservabilityGovernanceError(
            "profile comparison requires identical workload identity"
        )
    if baseline.environment_id != candidate.environment_id:
        raise ObservabilityGovernanceError(
            "profile comparison requires identical environment identity"
        )
    findings: list[PerformanceFinding] = []
    for phase in sorted(_PROFILE_PHASES):
        base = baseline.wall_ns_for(phase)
        current = candidate.wall_ns_for(phase)
        if base == 0 and current == 0:
            continue
        if base == 0:
            findings.append(
                PerformanceFinding(phase, base, current, PPM)
            )
            continue
        regression = max(0, ((current - base) * PPM) // base)
        if regression > threshold:
            findings.append(
                PerformanceFinding(phase, base, current, regression)
            )
    return tuple(findings)


# ---------------------------------------------------------------------------
# VOL-185: Latency budgeting with explicit retry cost
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LatencyStage:
    stage_id: str
    budget_us: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_id", _token("stage_id", self.stage_id))
        object.__setattr__(
            self, "budget_us", _integer("budget_us", self.budget_us, minimum=1)
        )


@dataclass(frozen=True, slots=True)
class LatencyBudget:
    budget_id: str
    operation_class: str
    environment: str
    percentile: str
    total_budget_us: int
    stages: tuple[LatencyStage, ...]

    def __post_init__(self) -> None:
        for name in ("budget_id", "operation_class", "environment"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        if self.percentile not in {"p50", "p95", "p99", "p999"}:
            raise ObservabilityGovernanceError("unsupported latency percentile")
        object.__setattr__(
            self,
            "total_budget_us",
            _integer("total_budget_us", self.total_budget_us, minimum=1),
        )
        stages = tuple(sorted(self.stages, key=lambda item: item.stage_id))
        if not stages:
            raise ObservabilityGovernanceError("latency budget requires stages")
        ids = [stage.stage_id for stage in stages]
        if len(ids) != len(set(ids)):
            raise ObservabilityGovernanceError("duplicate latency stage")
        if sum(stage.budget_us for stage in stages) > self.total_budget_us:
            raise ObservabilityGovernanceError(
                "stage budgets may not oversubscribe total latency budget"
            )
        object.__setattr__(self, "stages", stages)


@dataclass(frozen=True, slots=True)
class LatencyObservation:
    request_id: str
    stage_id: str
    attempt: int
    duration_us: int
    successful: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _token("request_id", self.request_id))
        object.__setattr__(self, "stage_id", _token("stage_id", self.stage_id))
        object.__setattr__(self, "attempt", _integer("attempt", self.attempt, minimum=1))
        object.__setattr__(
            self, "duration_us", _integer("duration_us", self.duration_us)
        )
        if not isinstance(self.successful, bool):
            raise ObservabilityGovernanceError("successful must be boolean")


@dataclass(frozen=True, slots=True)
class LatencyDecision:
    budget_id: str
    within_budget: bool
    total_observed_us: int
    retry_overhead_us: int
    exceeded_stages: tuple[str, ...]
    reason_code: str
    degradation_visible: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "budget_id", _token("budget_id", self.budget_id))
        if not isinstance(self.within_budget, bool):
            raise ObservabilityGovernanceError("within_budget must be boolean")
        object.__setattr__(
            self,
            "total_observed_us",
            _integer("total_observed_us", self.total_observed_us),
        )
        object.__setattr__(
            self,
            "retry_overhead_us",
            _integer("retry_overhead_us", self.retry_overhead_us),
        )
        object.__setattr__(
            self, "exceeded_stages", _tokens("exceeded_stage", self.exceeded_stages)
        )
        object.__setattr__(self, "reason_code", _token("reason_code", self.reason_code))
        if self.degradation_visible is not True:
            raise ObservabilityGovernanceError(
                "latency degradation may not be hidden"
            )


def evaluate_latency(
    budget: LatencyBudget,
    observations: Sequence[LatencyObservation],
) -> LatencyDecision:
    stage_budget = {stage.stage_id: stage.budget_us for stage in budget.stages}
    stage_totals = {stage.stage_id: 0 for stage in budget.stages}
    total = 0
    retry = 0
    seen: set[tuple[str, str, int]] = set()
    for observation in observations:
        identity = (
            observation.request_id,
            observation.stage_id,
            observation.attempt,
        )
        if identity in seen:
            raise ObservabilityGovernanceError("duplicate latency observation")
        seen.add(identity)
        if observation.stage_id not in stage_budget:
            raise ObservabilityGovernanceError(
                "unknown latency stage fails closed"
            )
        total += observation.duration_us
        stage_totals[observation.stage_id] += observation.duration_us
        if observation.attempt > 1:
            retry += observation.duration_us
    exceeded = tuple(
        sorted(
            stage_id
            for stage_id, observed in stage_totals.items()
            if observed > stage_budget[stage_id]
        )
    )
    within = total <= budget.total_budget_us and not exceeded
    reason = "within_latency_budget" if within else "latency_budget_exceeded"
    return LatencyDecision(
        budget.budget_id,
        within,
        total,
        retry,
        exceeded,
        reason,
    )


# ---------------------------------------------------------------------------
# VOL-186: Durable cost reservation, charge, refund, and safe fallback
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostReservation:
    reservation_id: str
    budget_id: str
    amount_microunits: int
    capability: str
    fallback_capability: str | None = None

    def __post_init__(self) -> None:
        for name in ("reservation_id", "budget_id", "capability"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(
            self,
            "amount_microunits",
            _integer(
                "amount_microunits", self.amount_microunits, minimum=1
            ),
        )
        if self.fallback_capability is not None:
            fallback = _token("fallback_capability", self.fallback_capability)
            if fallback == self.capability:
                raise ObservabilityGovernanceError(
                    "fallback capability must reduce or change capability"
                )
            object.__setattr__(self, "fallback_capability", fallback)


@dataclass(frozen=True, slots=True)
class CostCharge:
    charge_id: str
    reservation_id: str
    amount_microunits: int
    idempotency_key: str

    def __post_init__(self) -> None:
        for name in ("charge_id", "reservation_id", "idempotency_key"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(
            self,
            "amount_microunits",
            _integer(
                "amount_microunits", self.amount_microunits, minimum=1
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "charge_id": self.charge_id,
                "reservation_id": self.reservation_id,
                "amount_microunits": self.amount_microunits,
                "idempotency_key": self.idempotency_key,
            }
        )


@dataclass(frozen=True, slots=True)
class CostRefund:
    refund_id: str
    charge_id: str
    amount_microunits: int
    idempotency_key: str

    def __post_init__(self) -> None:
        for name in ("refund_id", "charge_id", "idempotency_key"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(
            self,
            "amount_microunits",
            _integer(
                "amount_microunits", self.amount_microunits, minimum=1
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "refund_id": self.refund_id,
                "charge_id": self.charge_id,
                "amount_microunits": self.amount_microunits,
                "idempotency_key": self.idempotency_key,
            }
        )


@dataclass(frozen=True, slots=True)
class CostDecision:
    allowed: bool
    reason_code: str
    remaining_microunits: int
    fallback_capability: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise ObservabilityGovernanceError("allowed must be boolean")
        object.__setattr__(self, "reason_code", _token("reason_code", self.reason_code))
        object.__setattr__(
            self,
            "remaining_microunits",
            _integer("remaining_microunits", self.remaining_microunits),
        )
        if self.fallback_capability is not None:
            object.__setattr__(
                self,
                "fallback_capability",
                _token("fallback_capability", self.fallback_capability),
            )


@dataclass(frozen=True, slots=True)
class CostLedger:
    budget_id: str
    limit_microunits: int
    safe_fallbacks: tuple[str, ...] = ()
    reservations: tuple[CostReservation, ...] = ()
    charges: tuple[CostCharge, ...] = ()
    refunds: tuple[CostRefund, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "budget_id", _token("budget_id", self.budget_id))
        object.__setattr__(
            self,
            "limit_microunits",
            _integer("limit_microunits", self.limit_microunits, minimum=1),
        )
        object.__setattr__(
            self, "safe_fallbacks", _tokens("safe_fallback", self.safe_fallbacks)
        )
        reservation_ids = [item.reservation_id for item in self.reservations]
        if len(reservation_ids) != len(set(reservation_ids)):
            raise ObservabilityGovernanceError("duplicate cost reservation identity")
        charge_ids = [item.charge_id for item in self.charges]
        if len(charge_ids) != len(set(charge_ids)):
            raise ObservabilityGovernanceError("duplicate cost charge identity")
        refund_ids = [item.refund_id for item in self.refunds]
        if len(refund_ids) != len(set(refund_ids)):
            raise ObservabilityGovernanceError("duplicate cost refund identity")
        if any(item.budget_id != self.budget_id for item in self.reservations):
            raise ObservabilityGovernanceError(
                "reservation belongs to a different cost budget"
            )

    @property
    def refunded_total(self) -> int:
        return sum(item.amount_microunits for item in self.refunds)

    @property
    def reserved_total(self) -> int:
        return sum(item.amount_microunits for item in self.reservations)

    @property
    def remaining_microunits(self) -> int:
        return max(
            0,
            self.limit_microunits - self.reserved_total + self.refunded_total,
        )


def reserve_cost(
    ledger: CostLedger,
    reservation: CostReservation,
) -> tuple[CostLedger, CostDecision]:
    if reservation.budget_id != ledger.budget_id:
        raise ObservabilityGovernanceError("reservation bound to wrong cost budget")
    existing = {
        item.reservation_id: item for item in ledger.reservations
    }.get(reservation.reservation_id)
    if existing is not None:
        if existing != reservation:
            raise ObservabilityGovernanceError(
                "reservation identity reused with different payload"
            )
        return (
            ledger,
            CostDecision(
                True,
                "reservation_idempotent_replay",
                ledger.remaining_microunits,
            ),
        )
    if reservation.amount_microunits > ledger.remaining_microunits:
        fallback = reservation.fallback_capability
        if fallback is not None and fallback in set(ledger.safe_fallbacks):
            return (
                ledger,
                CostDecision(
                    False,
                    "primary_cost_budget_exhausted_safe_fallback_available",
                    ledger.remaining_microunits,
                    fallback,
                ),
            )
        return (
            ledger,
            CostDecision(
                False,
                "cost_budget_exhausted",
                ledger.remaining_microunits,
            ),
        )
    updated = replace(
        ledger,
        reservations=ledger.reservations + (reservation,),
    )
    return (
        updated,
        CostDecision(
            True,
            "cost_reserved",
            updated.remaining_microunits,
        ),
    )


def charge_cost(ledger: CostLedger, charge: CostCharge) -> CostLedger:
    reservation = {
        item.reservation_id: item for item in ledger.reservations
    }.get(charge.reservation_id)
    if reservation is None:
        raise ObservabilityGovernanceError("charge references unknown reservation")
    by_key = {item.idempotency_key: item for item in ledger.charges}
    if charge.idempotency_key in by_key:
        if by_key[charge.idempotency_key].digest != charge.digest:
            raise ObservabilityGovernanceError(
                "charge idempotency key reused with different payload"
            )
        return ledger
    charged = sum(
        item.amount_microunits
        for item in ledger.charges
        if item.reservation_id == charge.reservation_id
    )
    if charged + charge.amount_microunits > reservation.amount_microunits:
        raise ObservabilityGovernanceError(
            "charge exceeds reserved cost authority"
        )
    return replace(ledger, charges=ledger.charges + (charge,))


def refund_cost(ledger: CostLedger, refund: CostRefund) -> CostLedger:
    charge = {item.charge_id: item for item in ledger.charges}.get(refund.charge_id)
    if charge is None:
        raise ObservabilityGovernanceError("refund references unknown charge")
    by_key = {item.idempotency_key: item for item in ledger.refunds}
    if refund.idempotency_key in by_key:
        if by_key[refund.idempotency_key].digest != refund.digest:
            raise ObservabilityGovernanceError(
                "refund idempotency key reused with different payload"
            )
        return ledger
    refunded = sum(
        item.amount_microunits
        for item in ledger.refunds
        if item.charge_id == refund.charge_id
    )
    if refunded + refund.amount_microunits > charge.amount_microunits:
        raise ObservabilityGovernanceError(
            "refund exceeds charged amount"
        )
    return replace(ledger, refunds=ledger.refunds + (refund,))


# ---------------------------------------------------------------------------
# VOL-187: Quality-equivalent compute/energy efficiency claims
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComputeObservation:
    observation_id: str
    workload_id: str
    hardware_class: str
    quality_ppm: int
    reliability_ppm: int
    work_units: int
    energy_millijoules: int
    compute_millis: int

    def __post_init__(self) -> None:
        for name in ("observation_id", "workload_id", "hardware_class"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(self, "quality_ppm", _ppm("quality_ppm", self.quality_ppm))
        object.__setattr__(
            self,
            "reliability_ppm",
            _ppm("reliability_ppm", self.reliability_ppm),
        )
        for name in ("work_units", "energy_millijoules", "compute_millis"):
            object.__setattr__(
                self, name, _integer(name, getattr(self, name), minimum=1)
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "observation_id": self.observation_id,
                "workload_id": self.workload_id,
                "hardware_class": self.hardware_class,
                "quality_ppm": self.quality_ppm,
                "reliability_ppm": self.reliability_ppm,
                "work_units": self.work_units,
                "energy_millijoules": self.energy_millijoules,
                "compute_millis": self.compute_millis,
            }
        )


@dataclass(frozen=True, slots=True)
class EfficiencyMetric:
    energy_per_million_units: int
    compute_millis_per_million_units: int

    def __post_init__(self) -> None:
        for name in (
            "energy_per_million_units",
            "compute_millis_per_million_units",
        ):
            object.__setattr__(
                self, name, _integer(name, getattr(self, name), minimum=1)
            )


@dataclass(frozen=True, slots=True)
class EfficiencyClaim:
    baseline_digest: str
    candidate_digest: str
    energy_improvement_ppm: int
    compute_improvement_ppm: int
    quality_delta_ppm: int
    reliability_delta_ppm: int
    valid: bool
    reason_code: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "baseline_digest", _hex("baseline_digest", self.baseline_digest, 64)
        )
        object.__setattr__(
            self,
            "candidate_digest",
            _hex("candidate_digest", self.candidate_digest, 64),
        )
        for name in (
            "energy_improvement_ppm",
            "compute_improvement_ppm",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ObservabilityGovernanceError(f"{name} must be integer")
        for name in ("quality_delta_ppm", "reliability_delta_ppm"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ObservabilityGovernanceError(f"{name} must be integer")
        if not isinstance(self.valid, bool):
            raise ObservabilityGovernanceError("valid must be boolean")
        object.__setattr__(self, "reason_code", _token("reason_code", self.reason_code))


def efficiency_metric(observation: ComputeObservation) -> EfficiencyMetric:
    energy = (
        observation.energy_millijoules * PPM + observation.work_units - 1
    ) // observation.work_units
    compute = (
        observation.compute_millis * PPM + observation.work_units - 1
    ) // observation.work_units
    return EfficiencyMetric(energy, compute)


def _improvement_ppm(baseline: int, candidate: int) -> int:
    return ((baseline - candidate) * PPM) // baseline


def evaluate_efficiency(
    baseline: ComputeObservation,
    candidate: ComputeObservation,
    *,
    min_energy_improvement_ppm: int = 10_000,
    max_quality_loss_ppm: int = 0,
    max_reliability_loss_ppm: int = 0,
) -> EfficiencyClaim:
    min_improvement = _ppm(
        "min_energy_improvement_ppm", min_energy_improvement_ppm
    )
    max_quality_loss = _ppm("max_quality_loss_ppm", max_quality_loss_ppm)
    max_reliability_loss = _ppm(
        "max_reliability_loss_ppm", max_reliability_loss_ppm
    )
    if baseline.workload_id != candidate.workload_id:
        raise ObservabilityGovernanceError(
            "efficiency comparison requires identical workload identity"
        )
    if baseline.hardware_class != candidate.hardware_class:
        raise ObservabilityGovernanceError(
            "efficiency comparison requires identical hardware class"
        )
    base_metric = efficiency_metric(baseline)
    cand_metric = efficiency_metric(candidate)
    energy_improvement = _improvement_ppm(
        base_metric.energy_per_million_units,
        cand_metric.energy_per_million_units,
    )
    compute_improvement = _improvement_ppm(
        base_metric.compute_millis_per_million_units,
        cand_metric.compute_millis_per_million_units,
    )
    quality_delta = candidate.quality_ppm - baseline.quality_ppm
    reliability_delta = candidate.reliability_ppm - baseline.reliability_ppm

    quality_ok = quality_delta >= -max_quality_loss
    reliability_ok = reliability_delta >= -max_reliability_loss
    energy_ok = energy_improvement >= min_improvement
    compute_ok = compute_improvement >= 0

    if not quality_ok:
        reason = "quality_equivalence_failed"
    elif not reliability_ok:
        reason = "reliability_equivalence_failed"
    elif not energy_ok:
        reason = "energy_improvement_insufficient"
    elif not compute_ok:
        reason = "compute_efficiency_regressed"
    else:
        reason = "quality_equivalent_efficiency_gain"

    return EfficiencyClaim(
        baseline.digest,
        candidate.digest,
        energy_improvement,
        compute_improvement,
        quality_delta,
        reliability_delta,
        quality_ok and reliability_ok and energy_ok and compute_ok,
        reason,
    )
