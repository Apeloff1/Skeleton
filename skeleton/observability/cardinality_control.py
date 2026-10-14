"""Fail-closed telemetry cardinality governance for the AI runtime.

This module governs metric label schemas and sampling declarations. Sampling
cannot legitimize secret/user-content labels or an over-cardinality schema.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import prod


_SOURCE_KINDS=frozenset({"bounded","system_id","user_content","secret"})
_SENSITIVE_LABEL_NAMES=frozenset({
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
    "api_key",
    "private_key",
    "prompt",
    "user_content",
})
_SENSITIVE_LABEL_SUFFIXES=(
    "_credential",
    "_credentials",
    "_password",
    "_secret",
    "_token",
    "_api_key",
    "_private_key",
    "_prompt",
    "_content",
)


class CardinalityControlError(ValueError):
    """A telemetry cardinality or sampling invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value,str) or not value or value != value.strip():
        raise CardinalityControlError(f"{name} must be non-empty normalized text")
    if len(value)>256:
        raise CardinalityControlError(f"{name} exceeds maximum length")
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value,bool) or not isinstance(value,int) or value<=0:
        raise CardinalityControlError(f"{name} must be a positive integer")
    return value


def _ppm(name: str, value: object) -> int:
    if isinstance(value,bool) or not isinstance(value,int) or not 0 <= value <= 1_000_000:
        raise CardinalityControlError(f"{name} must be an integer within [0, 1000000]")
    return value


def _digest(value: object) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TelemetryLabel:
    """Declared telemetry dimension; never raw telemetry payload."""

    name: str
    source_kind: str
    max_distinct_values: int
    exception_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self,"name",_token("name",self.name))
        normalized_name=self.name.lower().replace("-","_")
        if (
            normalized_name in _SENSITIVE_LABEL_NAMES
            or normalized_name.endswith(_SENSITIVE_LABEL_SUFFIXES)
        ):
            raise CardinalityControlError(
                "sensitive-looking telemetry label names are forbidden"
            )
        source=_token("source_kind",self.source_kind)
        if source not in _SOURCE_KINDS:
            raise CardinalityControlError("unknown telemetry label source kind")
        if source in {"secret","user_content"}:
            raise CardinalityControlError(
                "secret or user-content telemetry dimensions are forbidden"
            )
        object.__setattr__(self,"source_kind",source)
        object.__setattr__(
            self,
            "max_distinct_values",
            _positive_int("max_distinct_values",self.max_distinct_values),
        )
        if self.exception_reason is not None:
            object.__setattr__(
                self,
                "exception_reason",
                _token("exception_reason",self.exception_reason),
            )

    @property
    def digest(self) -> str:
        return _digest({
            "name":self.name,
            "source_kind":self.source_kind,
            "max_distinct_values":self.max_distinct_values,
            "exception_reason":self.exception_reason,
        })


@dataclass(frozen=True, slots=True)
class CardinalityBudget:
    metric_id: str
    max_series: int
    per_label_soft_limit: int
    high_cardinality_exceptions: tuple[str,...]=()

    def __post_init__(self) -> None:
        object.__setattr__(self,"metric_id",_token("metric_id",self.metric_id))
        object.__setattr__(self,"max_series",_positive_int("max_series",self.max_series))
        object.__setattr__(
            self,
            "per_label_soft_limit",
            _positive_int("per_label_soft_limit",self.per_label_soft_limit),
        )
        exceptions=tuple(sorted({_token("exception_label",v) for v in self.high_cardinality_exceptions}))
        object.__setattr__(self,"high_cardinality_exceptions",exceptions)

    @property
    def digest(self) -> str:
        return _digest({
            "metric_id":self.metric_id,
            "max_series":self.max_series,
            "per_label_soft_limit":self.per_label_soft_limit,
            "high_cardinality_exceptions":list(self.high_cardinality_exceptions),
        })


@dataclass(frozen=True, slots=True)
class SamplingPolicy:
    metric_id: str
    sample_rate_ppm: int
    max_events_per_window: int

    def __post_init__(self) -> None:
        object.__setattr__(self,"metric_id",_token("metric_id",self.metric_id))
        object.__setattr__(self,"sample_rate_ppm",_ppm("sample_rate_ppm",self.sample_rate_ppm))
        object.__setattr__(
            self,
            "max_events_per_window",
            _positive_int("max_events_per_window",self.max_events_per_window),
        )

    @property
    def digest(self) -> str:
        return _digest({
            "metric_id":self.metric_id,
            "sample_rate_ppm":self.sample_rate_ppm,
            "max_events_per_window":self.max_events_per_window,
        })


@dataclass(frozen=True, slots=True)
class CardinalityDecision:
    budget_digest: str
    sampling_policy_digest: str
    projected_max_series: int
    accepted: bool
    reasons: tuple[str,...]
    sampling_override: bool=False

    def __post_init__(self) -> None:
        for name in ("budget_digest","sampling_policy_digest"):
            value=getattr(self,name)
            if (
                not isinstance(value,str)
                or len(value)!=64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise CardinalityControlError(f"{name} must be lowercase sha256")
        object.__setattr__(
            self,
            "projected_max_series",
            _positive_int("projected_max_series",self.projected_max_series),
        )
        if not isinstance(self.accepted,bool):
            raise CardinalityControlError("accepted must be boolean")
        reasons=tuple(sorted(set(self.reasons)))
        if any(not isinstance(x,str) or not x for x in reasons):
            raise CardinalityControlError("reasons must contain non-empty strings")
        object.__setattr__(self,"reasons",reasons)
        if self.sampling_override is not False:
            raise CardinalityControlError("sampling cannot override cardinality policy")

    @property
    def digest(self) -> str:
        return _digest({
            "budget_digest":self.budget_digest,
            "sampling_policy_digest":self.sampling_policy_digest,
            "projected_max_series":self.projected_max_series,
            "accepted":self.accepted,
            "reasons":list(self.reasons),
            "sampling_override":False,
        })


def assess_cardinality(
    *,
    budget: CardinalityBudget,
    labels: tuple[TelemetryLabel,...],
    sampling_policy: SamplingPolicy,
) -> CardinalityDecision:
    if not isinstance(budget,CardinalityBudget):
        raise TypeError("budget must be CardinalityBudget")
    if not isinstance(sampling_policy,SamplingPolicy):
        raise TypeError("sampling_policy must be SamplingPolicy")
    if sampling_policy.metric_id != budget.metric_id:
        raise CardinalityControlError("sampling policy belongs to a different metric")
    if any(not isinstance(label,TelemetryLabel) for label in labels):
        raise CardinalityControlError("labels must contain TelemetryLabel values")
    names=[label.name for label in labels]
    if len(names)!=len(set(names)):
        raise CardinalityControlError("telemetry label names must be unique")

    reasons:list[str]=[]
    exception_set=set(budget.high_cardinality_exceptions)
    for label in labels:
        if label.max_distinct_values > budget.per_label_soft_limit:
            if label.name not in exception_set:
                reasons.append(f"high-cardinality-label:{label.name}")
            elif not label.exception_reason:
                reasons.append(f"missing-exception-reason:{label.name}")

    projected=prod(
        (label.max_distinct_values for label in labels),
        start=1,
    )
    if projected > budget.max_series:
        reasons.append("projected-series-exceeds-budget")

    normalized=tuple(sorted(set(reasons)))
    return CardinalityDecision(
        budget_digest=budget.digest,
        sampling_policy_digest=sampling_policy.digest,
        projected_max_series=projected,
        accepted=not normalized,
        reasons=normalized,
    )


__all__=[
    "CardinalityBudget",
    "CardinalityControlError",
    "CardinalityDecision",
    "SamplingPolicy",
    "TelemetryLabel",
    "assess_cardinality",
]
