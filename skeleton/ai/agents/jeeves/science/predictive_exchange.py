"""Prequential, lineage-aware exchange for heterogeneous predictive experts.

This is the treaty layer between forecasting implementations. A Holt smoother,
state-space model, HMM, boosted tree, spectral model, neural model or foundation
model may use completely different internals, but none may bypass these rules:

* each expert identifies the historical technique it implements;
* information used by a forecast stops at or before issuance;
* issuance precedes the target;
* routing weights are frozen at issuance;
* outcomes update only later forecasts, never earlier ones;
* scoring rules keep their mathematical semantics (binary log loss is
  non-negative; continuous negative log density need not be);
* routing compares like targets and domains rather than mixing incomparable
  score histories;
* mixtures preserve components and disagreement whenever representable;
* point forecasts are never assigned a fake probability density;
* every artifact has deterministic custody fingerprints.

The exchange deliberately does not name a globally best model. It produces the
prequential evidence consumed by :mod:`chronological_frontier`.
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from ..agent.types import (
    AgentContractError,
    finite_number,
    json_safe,
    positive_int,
    probability,
    stable_fingerprint,
    stable_id,
)
from .chronological_frontier import ForecastFamily, HistoricalEvaluation, TechniqueRegistry

_EPS = 1e-12


class PredictiveTargetKind(str, Enum):
    BINARY = "binary"
    CONTINUOUS = "continuous"


class ForecastShape(str, Enum):
    BERNOULLI = "bernoulli"
    GAUSSIAN = "gaussian"
    POINT = "point"
    MIXTURE = "mixture"


class ScoreAvailability(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class PredictiveTarget:
    target_id: str
    kind: PredictiveTargetKind
    target_time: float
    domain: str
    benchmark_id: str
    target_window_fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        target_id = str(self.target_id).strip()
        if not target_id:
            raise AgentContractError("target_id is required")
        object.__setattr__(self, "target_id", target_id)
        if not isinstance(self.kind, PredictiveTargetKind):
            object.__setattr__(self, "kind", PredictiveTargetKind(str(self.kind)))
        object.__setattr__(self, "target_time", finite_number("target_time", self.target_time))
        domain = str(self.domain).strip().casefold()
        benchmark = str(self.benchmark_id).strip()
        window = str(self.target_window_fingerprint).strip()
        if not domain or not benchmark or not window:
            raise AgentContractError("domain, benchmark_id and target_window_fingerprint are required")
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "benchmark_id", benchmark)
        object.__setattr__(self, "target_window_fingerprint", window)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.target_id,
                "kind": self.kind.value,
                "time": self.target_time,
                "domain": self.domain,
                "benchmark": self.benchmark_id,
                "window": self.target_window_fingerprint,
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class ExpertIdentity:
    expert_id: str
    technique_id: str
    model_version: str
    family: ForecastFamily
    code_fingerprint: str
    configuration_fingerprint: str
    training_data_fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "expert_id",
            "technique_id",
            "model_version",
            "code_fingerprint",
            "configuration_fingerprint",
            "training_data_fingerprint",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise AgentContractError(f"{name} is required")
            object.__setattr__(
                self,
                name,
                value.casefold() if name in {"expert_id", "technique_id"} else value,
            )
        if not isinstance(self.family, ForecastFamily):
            object.__setattr__(self, "family", ForecastFamily(str(self.family)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "expert": self.expert_id,
                "technique": self.technique_id,
                "version": self.model_version,
                "family": self.family.value,
                "code": self.code_fingerprint,
                "config": self.configuration_fingerprint,
                "training": self.training_data_fingerprint,
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class DistributionComponent:
    weight: float
    shape: ForecastShape
    probability_value: float | None = None
    mean: float | None = None
    standard_deviation: float | None = None
    source_expert_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "weight", probability("component weight", self.weight))
        if not isinstance(self.shape, ForecastShape):
            object.__setattr__(self, "shape", ForecastShape(str(self.shape)))
        if self.shape is ForecastShape.BERNOULLI:
            if self.probability_value is None:
                raise AgentContractError("Bernoulli component requires probability_value")
            object.__setattr__(
                self,
                "probability_value",
                probability("component probability", self.probability_value),
            )
            if self.mean is not None or self.standard_deviation is not None:
                raise AgentContractError("Bernoulli component cannot carry continuous parameters")
        elif self.shape is ForecastShape.GAUSSIAN:
            if self.mean is None or self.standard_deviation is None:
                raise AgentContractError("Gaussian component requires mean and standard_deviation")
            object.__setattr__(self, "mean", finite_number("component mean", self.mean))
            sd = finite_number("component standard_deviation", self.standard_deviation)
            if sd <= 0:
                raise AgentContractError("Gaussian standard_deviation must be positive")
            object.__setattr__(self, "standard_deviation", sd)
            if self.probability_value is not None:
                raise AgentContractError("Gaussian component cannot carry probability_value")
        elif self.shape is ForecastShape.POINT:
            if self.mean is None:
                raise AgentContractError("point component requires mean")
            object.__setattr__(self, "mean", finite_number("component mean", self.mean))
            if self.probability_value is not None or self.standard_deviation is not None:
                raise AgentContractError("point component has incompatible fields")
        else:
            raise AgentContractError("nested mixture components are not supported")
        if self.source_expert_id is not None:
            object.__setattr__(self, "source_expert_id", str(self.source_expert_id).strip().casefold())


@dataclass(frozen=True, slots=True)
class PredictiveDistribution:
    shape: ForecastShape
    probability_value: float | None = None
    mean: float | None = None
    standard_deviation: float | None = None
    components: tuple[DistributionComponent, ...] = ()
    quantiles: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.shape, ForecastShape):
            object.__setattr__(self, "shape", ForecastShape(str(self.shape)))
        if self.shape is ForecastShape.BERNOULLI:
            if self.probability_value is None:
                raise AgentContractError("Bernoulli forecast requires probability_value")
            object.__setattr__(
                self,
                "probability_value",
                probability("forecast probability", self.probability_value),
            )
            if self.mean is not None or self.standard_deviation is not None or self.components:
                raise AgentContractError("Bernoulli forecast has incompatible fields")
        elif self.shape is ForecastShape.POINT:
            if self.mean is None:
                raise AgentContractError("point forecast requires mean")
            object.__setattr__(self, "mean", finite_number("forecast mean", self.mean))
            if self.probability_value is not None or self.standard_deviation is not None or self.components:
                raise AgentContractError("point forecast has incompatible fields")
        elif self.shape is ForecastShape.GAUSSIAN:
            if self.mean is None or self.standard_deviation is None:
                raise AgentContractError("Gaussian forecast requires mean and standard_deviation")
            object.__setattr__(self, "mean", finite_number("forecast mean", self.mean))
            sd = finite_number("forecast standard_deviation", self.standard_deviation)
            if sd <= 0:
                raise AgentContractError("forecast standard_deviation must be positive")
            object.__setattr__(self, "standard_deviation", sd)
            if self.probability_value is not None or self.components:
                raise AgentContractError("Gaussian forecast has incompatible fields")
        elif self.shape is ForecastShape.MIXTURE:
            if not self.components:
                raise AgentContractError("mixture forecast requires components")
            total = sum(component.weight for component in self.components)
            if total <= 0:
                raise AgentContractError("mixture weights sum to zero")
            normalized = tuple(
                DistributionComponent(
                    weight=component.weight / total,
                    shape=component.shape,
                    probability_value=component.probability_value,
                    mean=component.mean,
                    standard_deviation=component.standard_deviation,
                    source_expert_id=component.source_expert_id,
                )
                for component in self.components
            )
            shapes = {component.shape for component in normalized}
            binary = shapes <= {ForecastShape.BERNOULLI}
            continuous = shapes <= {ForecastShape.GAUSSIAN, ForecastShape.POINT}
            if not (binary or continuous):
                raise AgentContractError("mixture cannot combine binary and continuous components")
            object.__setattr__(self, "components", normalized)
            if self.probability_value is not None or self.mean is not None or self.standard_deviation is not None:
                raise AgentContractError("mixture summary fields are derived, not supplied")
        else:  # pragma: no cover - exhaustive enum guard
            raise AgentContractError(f"unsupported forecast shape: {self.shape}")

        quantiles: dict[str, float] = {}
        for key, value in self.quantiles.items():
            try:
                q = float(str(key).strip())
            except ValueError as exc:
                raise AgentContractError(f"invalid quantile key: {key}") from exc
            if not 0.0 < q < 1.0:
                raise AgentContractError("quantile keys must lie strictly inside (0,1)")
            quantiles[format(q, ".12g")] = finite_number("quantile value", value)
        object.__setattr__(self, "quantiles", quantiles)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def target_kind(self) -> PredictiveTargetKind:
        if self.shape is ForecastShape.BERNOULLI:
            return PredictiveTargetKind.BINARY
        if self.shape is ForecastShape.MIXTURE and all(
            component.shape is ForecastShape.BERNOULLI for component in self.components
        ):
            return PredictiveTargetKind.BINARY
        return PredictiveTargetKind.CONTINUOUS

    @property
    def expected_value(self) -> float:
        if self.shape is ForecastShape.BERNOULLI:
            assert self.probability_value is not None
            return self.probability_value
        if self.shape in {ForecastShape.POINT, ForecastShape.GAUSSIAN}:
            assert self.mean is not None
            return self.mean
        if self.target_kind is PredictiveTargetKind.BINARY:
            return sum(
                component.weight * float(component.probability_value)
                for component in self.components
            )
        return sum(component.weight * float(component.mean) for component in self.components)

    @property
    def variance(self) -> float:
        if self.shape is ForecastShape.BERNOULLI:
            p = self.expected_value
            return p * (1.0 - p)
        if self.shape is ForecastShape.POINT:
            return 0.0
        if self.shape is ForecastShape.GAUSSIAN:
            assert self.standard_deviation is not None
            return self.standard_deviation**2
        mean = self.expected_value
        if self.target_kind is PredictiveTargetKind.BINARY:
            return mean * (1.0 - mean)
        total = 0.0
        for component in self.components:
            component_mean = float(component.mean)
            within = 0.0
            if component.shape is ForecastShape.GAUSSIAN:
                assert component.standard_deviation is not None
                within = component.standard_deviation**2
            total += component.weight * (within + (component_mean - mean) ** 2)
        return max(0.0, total)

    @property
    def epistemic_disagreement(self) -> float:
        if self.shape is not ForecastShape.MIXTURE or len(self.components) < 2:
            return 0.0
        mean = self.expected_value
        values = [
            float(component.probability_value)
            if component.shape is ForecastShape.BERNOULLI
            else float(component.mean)
            for component in self.components
        ]
        return sum(
            component.weight * (value - mean) ** 2
            for component, value in zip(self.components, values)
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "shape": self.shape.value,
                "probability": self.probability_value,
                "mean": self.mean,
                "sd": self.standard_deviation,
                "components": [
                    (
                        component.weight,
                        component.shape.value,
                        component.probability_value,
                        component.mean,
                        component.standard_deviation,
                        component.source_expert_id,
                    )
                    for component in self.components
                ],
                "quantiles": dict(sorted(self.quantiles.items())),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class ForecastRequest:
    request_id: str
    target: PredictiveTarget
    issued_at: float
    information_cutoff: float
    as_of_year: int
    features: Mapping[str, Any] = field(default_factory=dict)
    provenance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        request_id = str(self.request_id).strip()
        if not request_id:
            raise AgentContractError("request_id is required")
        object.__setattr__(self, "request_id", request_id)
        issued = finite_number("issued_at", self.issued_at)
        cutoff = finite_number("information_cutoff", self.information_cutoff)
        if cutoff > issued:
            raise AgentContractError("information_cutoff cannot exceed issuance time")
        if issued >= self.target.target_time:
            raise AgentContractError("forecast issuance must precede target_time")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "information_cutoff", cutoff)
        if isinstance(self.as_of_year, bool) or not isinstance(self.as_of_year, int):
            raise AgentContractError("as_of_year must be integer")
        object.__setattr__(self, "features", json_safe(dict(self.features)))
        object.__setattr__(
            self,
            "provenance_ids",
            tuple(sorted({str(item) for item in self.provenance_ids if str(item)})),
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "request": self.request_id,
                "target": self.target.fingerprint,
                "issued": self.issued_at,
                "cutoff": self.information_cutoff,
                "as_of_year": self.as_of_year,
                "features": dict(self.features),
                "provenance": self.provenance_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class ForecastEnvelope:
    forecast_id: str
    request_fingerprint: str
    target_id: str
    expert: ExpertIdentity
    issued_at: float
    information_cutoff: float
    distribution: PredictiveDistribution
    evidence_ids: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(
            str(value).strip()
            for value in (self.forecast_id, self.request_fingerprint, self.target_id)
        ):
            raise AgentContractError("forecast identity fields are required")
        issued = finite_number("forecast issued_at", self.issued_at)
        cutoff = finite_number("forecast information_cutoff", self.information_cutoff)
        if cutoff > issued:
            raise AgentContractError("forecast information_cutoff cannot exceed issued_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "information_cutoff", cutoff)
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(sorted({str(item) for item in self.evidence_ids if str(item)})),
        )
        object.__setattr__(self, "diagnostics", json_safe(dict(self.diagnostics)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.forecast_id,
                "request": self.request_fingerprint,
                "target": self.target_id,
                "expert": self.expert.fingerprint,
                "issued": self.issued_at,
                "cutoff": self.information_cutoff,
                "distribution": self.distribution.fingerprint,
                "evidence": self.evidence_ids,
                "diagnostics": dict(self.diagnostics),
            }
        )


@runtime_checkable
class ForecastExpert(Protocol):
    @property
    def identity(self) -> ExpertIdentity: ...

    def forecast(self, request: ForecastRequest) -> ForecastEnvelope: ...


class ForecastExpertRegistry:
    def __init__(self, technique_registry: TechniqueRegistry) -> None:
        self.techniques = technique_registry
        self._experts: dict[str, ForecastExpert] = {}

    def register(self, expert: ForecastExpert) -> None:
        if not hasattr(expert, "identity") or not callable(getattr(expert, "forecast", None)):
            raise TypeError("expert must provide identity and forecast(request)")
        identity = expert.identity
        if not isinstance(identity, ExpertIdentity):
            raise TypeError("expert.identity must be ExpertIdentity")
        technique = self.techniques.get(identity.technique_id)
        if technique.family is not identity.family:
            raise AgentContractError(
                f"expert family {identity.family.value} does not match lineage family {technique.family.value}"
            )
        existing = self._experts.get(identity.expert_id)
        if existing is not None and existing.identity.fingerprint != identity.fingerprint:
            raise AgentContractError(f"expert identity collision: {identity.expert_id}")
        self._experts[identity.expert_id] = expert

    def get(self, expert_id: str) -> ForecastExpert:
        key = str(expert_id).strip().casefold()
        try:
            return self._experts[key]
        except KeyError as exc:
            raise AgentContractError(f"unknown forecast expert: {key}") from exc

    def eligible(
        self,
        as_of_year: int,
        *,
        kind: PredictiveTargetKind | None = None,
    ) -> tuple[ForecastExpert, ...]:
        result: list[ForecastExpert] = []
        for expert in self._experts.values():
            technique = self.techniques.get(expert.identity.technique_id)
            if technique.available_year > as_of_year:
                continue
            supported = expert.identity.metadata.get("target_kinds")
            if kind is not None and isinstance(supported, list) and kind.value not in supported:
                continue
            result.append(expert)
        result.sort(
            key=lambda item: (
                self.techniques.get(item.identity.technique_id).available_year,
                item.identity.expert_id,
            )
        )
        return tuple(result)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            [(key, expert.identity.fingerprint) for key, expert in sorted(self._experts.items())]
        )


@dataclass(frozen=True, slots=True)
class ForecastScore:
    score_id: str
    forecast_id: str
    forecast_fingerprint: str
    expert_id: str
    technique_id: str
    target_id: str
    target_kind: PredictiveTargetKind
    domain: str
    benchmark_id: str
    target_window_fingerprint: str
    issued_at: float
    target_time: float
    resolved_at: float
    absolute_error: float
    squared_error: float
    log_score_loss: float | None = None
    brier: float | None = None
    gaussian_crps: float | None = None
    standardized_residual: float | None = None
    outcome: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PredictiveTargetKind):
            object.__setattr__(self, "target_kind", PredictiveTargetKind(str(self.target_kind)))
        issued = finite_number("issued_at", self.issued_at)
        target = finite_number("target_time", self.target_time)
        resolved = finite_number("resolved_at", self.resolved_at)
        if not issued < target <= resolved:
            raise AgentContractError("score custody requires issued_at < target_time <= resolved_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "target_time", target)
        object.__setattr__(self, "resolved_at", resolved)
        for name in ("absolute_error", "squared_error"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        # Negative continuous log density is mathematically valid when density
        # exceeds one. Therefore only finiteness is universal here.
        if self.log_score_loss is not None:
            object.__setattr__(
                self,
                "log_score_loss",
                finite_number("log_score_loss", self.log_score_loss),
            )
        for name in ("brier", "gaussian_crps"):
            value = getattr(self, name)
            if value is not None:
                value = finite_number(name, value)
                if value < 0:
                    raise AgentContractError(f"{name} must be non-negative")
                object.__setattr__(self, name, value)
        if self.standardized_residual is not None:
            object.__setattr__(
                self,
                "standardized_residual",
                finite_number("standardized_residual", self.standardized_residual),
            )
        object.__setattr__(self, "outcome", finite_number("outcome", self.outcome))
        for name in ("domain", "benchmark_id", "target_window_fingerprint"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise AgentContractError(f"{name} is required")
            object.__setattr__(self, name, value.casefold() if name == "domain" else value)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.score_id,
                "forecast": self.forecast_fingerprint,
                "expert": self.expert_id,
                "technique": self.technique_id,
                "target": self.target_id,
                "kind": self.target_kind.value,
                "domain": self.domain,
                "benchmark": self.benchmark_id,
                "window": self.target_window_fingerprint,
                "issued": self.issued_at,
                "target_time": self.target_time,
                "resolved": self.resolved_at,
                "ae": self.absolute_error,
                "se": self.squared_error,
                "log": self.log_score_loss,
                "brier": self.brier,
                "crps": self.gaussian_crps,
                "z": self.standardized_residual,
                "outcome": self.outcome,
                "metadata": dict(self.metadata),
            }
        )


def _normal_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _gaussian_crps(mean: float, sd: float, outcome: float) -> float:
    z = (outcome - mean) / sd
    return sd * (
        z * (2.0 * _normal_cdf(z) - 1.0)
        + 2.0 * _normal_pdf(z)
        - 1.0 / math.sqrt(math.pi)
    )


def _continuous_log_loss(mean: float, sd: float, outcome: float) -> float:
    z = (outcome - mean) / sd
    return math.log(sd) + 0.5 * math.log(2.0 * math.pi) + 0.5 * z * z


def _gaussian_component_density(component: DistributionComponent, outcome: float) -> float:
    if component.shape is not ForecastShape.GAUSSIAN:
        raise AgentContractError("exact mixture density requires Gaussian components")
    assert component.standard_deviation is not None and component.mean is not None
    z = (outcome - component.mean) / component.standard_deviation
    return _normal_pdf(z) / component.standard_deviation


class PrequentialScoreLedger:
    """Append-only forecast/score custody ledger."""

    def __init__(self, *, max_forecasts: int = 2_000_000) -> None:
        self.max_forecasts = positive_int(
            "max_forecasts",
            max_forecasts,
            maximum=100_000_000,
        )
        self._forecasts: dict[str, tuple[ForecastEnvelope, PredictiveTarget]] = {}
        self._scores: dict[str, ForecastScore] = {}
        self._scores_by_expert: defaultdict[str, list[str]] = defaultdict(list)
        self._score_by_forecast: dict[str, str] = {}
        self._lock = threading.RLock()

    def record(self, request: ForecastRequest, envelope: ForecastEnvelope) -> ForecastEnvelope:
        if envelope.request_fingerprint != request.fingerprint:
            raise AgentContractError("forecast request fingerprint mismatch")
        if envelope.target_id != request.target.target_id:
            raise AgentContractError("forecast target mismatch")
        if (
            envelope.issued_at != request.issued_at
            or envelope.information_cutoff != request.information_cutoff
        ):
            raise AgentContractError("forecast temporal custody differs from request")
        if envelope.distribution.target_kind is not request.target.kind:
            raise AgentContractError("forecast distribution kind does not match target kind")
        forecast_id = str(envelope.forecast_id)
        with self._lock:
            existing = self._forecasts.get(forecast_id)
            if existing is not None:
                if existing[0].fingerprint != envelope.fingerprint:
                    raise AgentContractError(f"forecast id collision: {forecast_id}")
                return existing[0]
            if len(self._forecasts) >= self.max_forecasts:
                raise AgentContractError("prequential forecast ledger is full")
            self._forecasts[forecast_id] = (envelope, request.target)
        return envelope

    def resolve(
        self,
        forecast_id: str,
        outcome: bool | int | float,
        *,
        resolved_at: float,
    ) -> ForecastScore:
        resolved = finite_number("resolved_at", resolved_at)
        with self._lock:
            try:
                envelope, target = self._forecasts[str(forecast_id)]
            except KeyError as exc:
                raise AgentContractError(f"unknown forecast: {forecast_id}") from exc
            existing_id = self._score_by_forecast.get(envelope.forecast_id)
            if existing_id is not None:
                existing = self._scores[existing_id]
                same_outcome = existing.outcome == (float(bool(outcome)) if target.kind is PredictiveTargetKind.BINARY else float(outcome))
                if existing.resolved_at == resolved and same_outcome:
                    return existing
                raise AgentContractError("forecast is already resolved with a different outcome or timestamp")
            if resolved < target.target_time:
                raise AgentContractError("cannot resolve forecast before target_time")

            distribution = envelope.distribution
            score_id = stable_id(
                "forecast-score",
                {
                    "forecast": envelope.fingerprint,
                    "resolved_at": resolved,
                    "outcome": outcome,
                },
                length=32,
            )
            common = dict(
                score_id=score_id,
                forecast_id=envelope.forecast_id,
                forecast_fingerprint=envelope.fingerprint,
                expert_id=envelope.expert.expert_id,
                technique_id=envelope.expert.technique_id,
                target_id=target.target_id,
                target_kind=target.kind,
                domain=target.domain,
                benchmark_id=target.benchmark_id,
                target_window_fingerprint=target.target_window_fingerprint,
                issued_at=envelope.issued_at,
                target_time=target.target_time,
                resolved_at=resolved,
            )
            if target.kind is PredictiveTargetKind.BINARY:
                if outcome not in {0, 1, False, True}:
                    raise AgentContractError("binary outcome must be 0/1 or bool")
                y = 1.0 if bool(outcome) else 0.0
                p = distribution.expected_value
                clipped = min(1.0 - _EPS, max(_EPS, p))
                ae = abs(p - y)
                score = ForecastScore(
                    **common,
                    absolute_error=ae,
                    squared_error=ae**2,
                    log_score_loss=-(
                        y * math.log(clipped)
                        + (1.0 - y) * math.log(1.0 - clipped)
                    ),
                    brier=(p - y) ** 2,
                    outcome=y,
                    metadata={"scoring_rule": "bernoulli_log_and_brier"},
                )
            else:
                if isinstance(outcome, bool):
                    raise AgentContractError("continuous outcome cannot be bool")
                y = finite_number("continuous outcome", outcome)
                mean = distribution.expected_value
                ae = abs(mean - y)
                log_score_loss: float | None = None
                crps: float | None = None
                standardized: float | None = None
                scoring_rule = "point_error_only"
                if distribution.shape is ForecastShape.GAUSSIAN:
                    assert distribution.standard_deviation is not None
                    sd = distribution.standard_deviation
                    log_score_loss = _continuous_log_loss(mean, sd, y)
                    crps = _gaussian_crps(mean, sd, y)
                    standardized = (y - mean) / sd
                    scoring_rule = "gaussian_log_crps"
                elif (
                    distribution.shape is ForecastShape.MIXTURE
                    and distribution.components
                    and all(
                        component.shape is ForecastShape.GAUSSIAN
                        for component in distribution.components
                    )
                ):
                    density = sum(
                        component.weight * _gaussian_component_density(component, y)
                        for component in distribution.components
                    )
                    log_score_loss = -math.log(max(_EPS, density))
                    scoring_rule = "gaussian_mixture_log"
                score = ForecastScore(
                    **common,
                    absolute_error=ae,
                    squared_error=ae**2,
                    log_score_loss=log_score_loss,
                    gaussian_crps=crps,
                    standardized_residual=standardized,
                    outcome=y,
                    metadata={"scoring_rule": scoring_rule},
                )
            self._scores[score.score_id] = score
            self._score_by_forecast[score.forecast_id] = score.score_id
            self._scores_by_expert[score.expert_id].append(score.score_id)
            return score

    def scores(
        self,
        expert_id: str,
        *,
        available_before: float | None = None,
        target_kind: PredictiveTargetKind | None = None,
        domain: str | None = None,
        benchmark_id: str | None = None,
        target_window_fingerprint: str | None = None,
    ) -> tuple[ForecastScore, ...]:
        key = str(expert_id).strip().casefold()
        with self._lock:
            rows = [
                self._scores[score_id]
                for score_id in self._scores_by_expert.get(key, ())
            ]
        if available_before is not None:
            cutoff = finite_number("available_before", available_before)
            rows = [row for row in rows if row.resolved_at < cutoff]
        if target_kind is not None:
            rows = [row for row in rows if row.target_kind is target_kind]
        if domain is not None:
            domain_key = str(domain).strip().casefold()
            rows = [row for row in rows if row.domain == domain_key]
        if benchmark_id is not None:
            rows = [row for row in rows if row.benchmark_id == str(benchmark_id)]
        if target_window_fingerprint is not None:
            rows = [
                row
                for row in rows
                if row.target_window_fingerprint == str(target_window_fingerprint)
            ]
        rows.sort(key=lambda row: (row.resolved_at, row.target_time, row.score_id))
        return tuple(rows)

    def unresolved(self) -> tuple[ForecastEnvelope, ...]:
        with self._lock:
            rows = [
                envelope
                for forecast_id, (envelope, _) in self._forecasts.items()
                if forecast_id not in self._score_by_forecast
            ]
        rows.sort(key=lambda row: (row.issued_at, row.forecast_id))
        return tuple(rows)

    def aggregate(
        self,
        expert_id: str,
        *,
        available_before: float | None = None,
        target_kind: PredictiveTargetKind | None = None,
        domain: str | None = None,
        benchmark_id: str | None = None,
        target_window_fingerprint: str | None = None,
    ) -> Mapping[str, float]:
        rows = self.scores(
            expert_id,
            available_before=available_before,
            target_kind=target_kind,
            domain=domain,
            benchmark_id=benchmark_id,
            target_window_fingerprint=target_window_fingerprint,
        )
        if not rows:
            return {}
        count = len(rows)
        result: dict[str, float] = {
            "count": float(count),
            "mae": sum(row.absolute_error for row in rows) / count,
            "rmse": math.sqrt(sum(row.squared_error for row in rows) / count),
        }
        log_rows = [row.log_score_loss for row in rows if row.log_score_loss is not None]
        if log_rows:
            result["log_loss"] = sum(log_rows) / len(log_rows)
        brier_rows = [row.brier for row in rows if row.brier is not None]
        if brier_rows:
            result["brier"] = sum(brier_rows) / len(brier_rows)
        crps_rows = [row.gaussian_crps for row in rows if row.gaussian_crps is not None]
        if crps_rows:
            result["crps"] = sum(crps_rows) / len(crps_rows)
        z_rows = [
            row.standardized_residual
            for row in rows
            if row.standardized_residual is not None
        ]
        if z_rows:
            within_95 = sum(
                abs(value) <= 1.959963984540054 for value in z_rows
            ) / len(z_rows)
            result["coverage_gap"] = abs(within_95 - 0.95)
        return result

    @property
    def fingerprint(self) -> str:
        with self._lock:
            forecasts = [
                (key, value[0].fingerprint)
                for key, value in sorted(self._forecasts.items())
            ]
            scores = [
                (key, value.fingerprint)
                for key, value in sorted(self._scores.items())
            ]
        return stable_fingerprint({"forecasts": forecasts, "scores": scores})


@dataclass(frozen=True, slots=True)
class RouterPolicy:
    minimum_resolved_scores: int = 5
    loss_temperature: float = 0.35
    family_weight_cap: float = 0.70
    expert_weight_cap: float = 0.55
    cold_start_weight: float = 1.0
    same_domain_only: bool = True
    same_benchmark_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "minimum_resolved_scores",
            positive_int(
                "minimum_resolved_scores",
                self.minimum_resolved_scores,
                maximum=1_000_000,
            ),
        )
        temperature = finite_number("loss_temperature", self.loss_temperature)
        if temperature <= 0:
            raise AgentContractError("loss_temperature must be positive")
        object.__setattr__(self, "loss_temperature", temperature)
        for name in ("family_weight_cap", "expert_weight_cap"):
            value = probability(name, getattr(self, name))
            if value <= 0:
                raise AgentContractError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        cold = finite_number("cold_start_weight", self.cold_start_weight)
        if cold <= 0:
            raise AgentContractError("cold_start_weight must be positive")
        object.__setattr__(self, "cold_start_weight", cold)


@dataclass(frozen=True, slots=True)
class RoutingWeight:
    expert_id: str
    technique_id: str
    family: ForecastFamily
    weight: float
    resolved_scores_used: int
    historical_loss: float | None


@dataclass(frozen=True, slots=True)
class RoutingSnapshot:
    snapshot_id: str
    request_fingerprint: str
    issued_at: float
    weights: tuple[RoutingWeight, ...]
    score_ledger_fingerprint: str
    constraints_relaxed: tuple[str, ...]
    fingerprint: str


def _cap_simplex(weights: Sequence[float], cap: float) -> tuple[list[float], bool]:
    """Project non-negative weights onto a capped simplex when feasible."""

    n = len(weights)
    if n == 0:
        return [], True
    if cap * n < 1.0 - 1e-12:
        total = sum(weights)
        return [value / total for value in weights], False
    result = [max(0.0, float(value)) for value in weights]
    total = sum(result)
    if total <= 0:
        result = [1.0 / n] * n
    else:
        result = [value / total for value in result]
    fixed: set[int] = set()
    for _ in range(n + 2):
        offenders = [i for i, value in enumerate(result) if i not in fixed and value > cap + 1e-15]
        if not offenders:
            break
        for i in offenders:
            result[i] = cap
            fixed.add(i)
        free = [i for i in range(n) if i not in fixed]
        remaining = 1.0 - sum(result[i] for i in fixed)
        if not free:
            break
        free_total = sum(result[i] for i in free)
        if free_total <= 0:
            each = remaining / len(free)
            for i in free:
                result[i] = each
        else:
            for i in free:
                result[i] = remaining * result[i] / free_total
    total = sum(result)
    if total > 0:
        result = [value / total for value in result]
    return result, True


class PrequentialExpertRouter:
    """Route experts using only outcomes available before forecast issuance."""

    def __init__(
        self,
        registry: ForecastExpertRegistry,
        scores: PrequentialScoreLedger,
        *,
        policy: RouterPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.scores = scores
        self.policy = policy or RouterPolicy()

    @staticmethod
    def _loss(rows: Sequence[ForecastScore]) -> float:
        if not rows:
            return 0.0
        proper = [row.log_score_loss for row in rows if row.log_score_loss is not None]
        if proper:
            return sum(proper) / len(proper)
        return sum(row.absolute_error for row in rows) / len(rows)

    def _cap_weights(
        self,
        candidates: Sequence[tuple[ForecastExpert, float, int, float | None]],
    ) -> tuple[tuple[RoutingWeight, ...], tuple[str, ...]]:
        if not candidates:
            return (), ()
        raw_total = sum(item[1] for item in candidates)
        if raw_total <= 0:
            base = [1.0 / len(candidates)] * len(candidates)
        else:
            base = [item[1] / raw_total for item in candidates]
        relaxed: list[str] = []
        expert_weights, expert_feasible = _cap_simplex(base, self.policy.expert_weight_cap)
        if not expert_feasible:
            relaxed.append("expert_weight_cap_infeasible_for_candidate_count")

        families: defaultdict[ForecastFamily, list[int]] = defaultdict(list)
        for index, item in enumerate(candidates):
            families[item[0].identity.family].append(index)
        family_keys = sorted(families, key=lambda family: family.value)
        family_masses = [sum(expert_weights[i] for i in families[family]) for family in family_keys]
        capped_family_masses, family_feasible = _cap_simplex(
            family_masses,
            self.policy.family_weight_cap,
        )
        if not family_feasible:
            relaxed.append("family_weight_cap_infeasible_for_family_count")
        else:
            adjusted = expert_weights[:]
            for family, old_mass, new_mass in zip(
                family_keys,
                family_masses,
                capped_family_masses,
            ):
                indices = families[family]
                if old_mass <= _EPS:
                    each = new_mass / len(indices)
                    for i in indices:
                        adjusted[i] = each
                else:
                    scale = new_mass / old_mass
                    for i in indices:
                        adjusted[i] *= scale
            expert_weights = adjusted
            # Family projection can push an individual over its cap. Re-project
            # only if the expert cap is feasible, and record any resulting
            # family relaxation explicitly instead of pretending both held.
            if expert_feasible:
                projected, _ = _cap_simplex(expert_weights, self.policy.expert_weight_cap)
                new_family_masses = [sum(projected[i] for i in families[family]) for family in family_keys]
                if any(
                    mass > self.policy.family_weight_cap + 1e-10
                    for mass in new_family_masses
                ):
                    relaxed.append("joint_expert_family_caps_not_simultaneously_projected")
                expert_weights = projected

        total = sum(expert_weights)
        if total <= 0:
            expert_weights = [1.0 / len(candidates)] * len(candidates)
        else:
            expert_weights = [value / total for value in expert_weights]
        return (
            tuple(
                RoutingWeight(
                    expert_id=expert.identity.expert_id,
                    technique_id=expert.identity.technique_id,
                    family=expert.identity.family,
                    weight=max(0.0, min(1.0, weight)),
                    resolved_scores_used=count,
                    historical_loss=loss,
                )
                for (expert, _, count, loss), weight in zip(candidates, expert_weights)
            ),
            tuple(sorted(set(relaxed))),
        )

    def snapshot(self, request: ForecastRequest) -> RoutingSnapshot:
        experts = self.registry.eligible(request.as_of_year, kind=request.target.kind)
        if not experts:
            raise AgentContractError("no historically eligible predictive experts")
        scored: list[tuple[ForecastExpert, float, int, float | None]] = []
        for expert in experts:
            rows = self.scores.scores(
                expert.identity.expert_id,
                available_before=request.issued_at,
                target_kind=request.target.kind,
                domain=request.target.domain if self.policy.same_domain_only else None,
                benchmark_id=request.target.benchmark_id if self.policy.same_benchmark_only else None,
            )
            if len(rows) < self.policy.minimum_resolved_scores:
                scored.append((expert, self.policy.cold_start_weight, len(rows), None))
                continue
            loss = self._loss(rows)
            exponent = max(-60.0, min(60.0, -loss / self.policy.loss_temperature))
            scored.append((expert, max(_EPS, math.exp(exponent)), len(rows), loss))
        weights, relaxed = self._cap_weights(scored)
        snapshot_id = stable_id(
            "routing-snapshot",
            {
                "request": request.fingerprint,
                "issued": request.issued_at,
                "weights": [
                    (
                        item.expert_id,
                        item.technique_id,
                        item.family.value,
                        item.weight,
                        item.resolved_scores_used,
                        item.historical_loss,
                    )
                    for item in weights
                ],
                "relaxed": relaxed,
            },
            length=32,
        )
        payload = {
            "snapshot": snapshot_id,
            "request": request.fingerprint,
            "issued": request.issued_at,
            "weights": [
                (
                    item.expert_id,
                    item.technique_id,
                    item.family.value,
                    item.weight,
                    item.resolved_scores_used,
                    item.historical_loss,
                )
                for item in weights
            ],
            "relaxed": relaxed,
            "ledger": self.scores.fingerprint,
        }
        return RoutingSnapshot(
            snapshot_id=snapshot_id,
            request_fingerprint=request.fingerprint,
            issued_at=request.issued_at,
            weights=weights,
            score_ledger_fingerprint=self.scores.fingerprint,
            constraints_relaxed=relaxed,
            fingerprint=stable_fingerprint(payload),
        )


@dataclass(frozen=True, slots=True)
class EnsembleForecast:
    ensemble_id: str
    request_fingerprint: str
    routing_snapshot_id: str
    distribution: PredictiveDistribution
    component_forecast_ids: tuple[str, ...]
    component_fingerprints: tuple[str, ...]
    epistemic_disagreement: float
    fingerprint: str


class ForecastArbiter:
    """Execute experts and retain representable component uncertainty."""

    def __init__(
        self,
        registry: ForecastExpertRegistry,
        scores: PrequentialScoreLedger,
        router: PrequentialExpertRouter,
    ) -> None:
        self.registry = registry
        self.scores = scores
        self.router = router

    @staticmethod
    def _components(
        routing: RoutingWeight,
        distribution: PredictiveDistribution,
    ) -> list[DistributionComponent]:
        if distribution.shape is ForecastShape.MIXTURE:
            return [
                DistributionComponent(
                    weight=routing.weight * component.weight,
                    shape=component.shape,
                    probability_value=component.probability_value,
                    mean=component.mean,
                    standard_deviation=component.standard_deviation,
                    source_expert_id=routing.expert_id,
                )
                for component in distribution.components
            ]
        if distribution.shape is ForecastShape.BERNOULLI:
            return [
                DistributionComponent(
                    weight=routing.weight,
                    shape=ForecastShape.BERNOULLI,
                    probability_value=distribution.probability_value,
                    source_expert_id=routing.expert_id,
                )
            ]
        if distribution.shape is ForecastShape.GAUSSIAN:
            return [
                DistributionComponent(
                    weight=routing.weight,
                    shape=ForecastShape.GAUSSIAN,
                    mean=distribution.mean,
                    standard_deviation=distribution.standard_deviation,
                    source_expert_id=routing.expert_id,
                )
            ]
        return [
            DistributionComponent(
                weight=routing.weight,
                shape=ForecastShape.POINT,
                mean=distribution.mean,
                source_expert_id=routing.expert_id,
            )
        ]

    def predict(self, request: ForecastRequest) -> EnsembleForecast:
        snapshot = self.router.snapshot(request)
        envelopes: list[ForecastEnvelope] = []
        components: list[DistributionComponent] = []
        for routing in snapshot.weights:
            expert = self.registry.get(routing.expert_id)
            envelope = expert.forecast(request)
            if envelope.expert.fingerprint != expert.identity.fingerprint:
                raise AgentContractError("expert emitted forecast under a different identity")
            self.scores.record(request, envelope)
            envelopes.append(envelope)
            components.extend(self._components(routing, envelope.distribution))
        mixture = PredictiveDistribution(
            shape=ForecastShape.MIXTURE,
            components=tuple(components),
            metadata={
                "routing_snapshot": snapshot.snapshot_id,
                "component_count": len(components),
                "mixture_is_evidence_preserving": True,
                "routing_constraints_relaxed": list(snapshot.constraints_relaxed),
            },
        )
        ensemble_id = stable_id(
            "expert-ensemble",
            {
                "request": request.fingerprint,
                "routing": snapshot.fingerprint,
                "forecasts": [envelope.fingerprint for envelope in envelopes],
                "distribution": mixture.fingerprint,
            },
            length=32,
        )
        payload = {
            "ensemble": ensemble_id,
            "request": request.fingerprint,
            "routing": snapshot.snapshot_id,
            "distribution": mixture.fingerprint,
            "components": [envelope.fingerprint for envelope in envelopes],
        }
        return EnsembleForecast(
            ensemble_id=ensemble_id,
            request_fingerprint=request.fingerprint,
            routing_snapshot_id=snapshot.snapshot_id,
            distribution=mixture,
            component_forecast_ids=tuple(envelope.forecast_id for envelope in envelopes),
            component_fingerprints=tuple(envelope.fingerprint for envelope in envelopes),
            epistemic_disagreement=mixture.epistemic_disagreement,
            fingerprint=stable_fingerprint(payload),
        )


@dataclass(frozen=True, slots=True)
class HistoricalEvidencePolicy:
    minimum_scores: int = 20
    minimum_domains: int = 1
    minimum_independent_runs: int = 2

    def __post_init__(self) -> None:
        for name in ("minimum_scores", "minimum_domains", "minimum_independent_runs"):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=10_000_000),
            )


class HistoricalEvidenceBuilder:
    """Convert resolved prequential custody into tournament evidence."""

    def __init__(
        self,
        ledger: PrequentialScoreLedger,
        *,
        policy: HistoricalEvidencePolicy | None = None,
    ) -> None:
        self.ledger = ledger
        self.policy = policy or HistoricalEvidencePolicy()

    def build(
        self,
        identity: ExpertIdentity,
        *,
        as_of_year: int,
        benchmark_id: str,
        target_window_fingerprint: str,
        knowledge_year: int,
        data_cutoff_year: int,
        available_before: float,
        domain_count: int,
        independent_runs: int,
        calibration_ece: float | None = None,
        calibration_checked: bool = False,
        provenance_ids: Sequence[str] = (),
    ) -> HistoricalEvaluation:
        rows = self.ledger.scores(
            identity.expert_id,
            available_before=available_before,
            benchmark_id=benchmark_id,
            target_window_fingerprint=target_window_fingerprint,
        )
        rows = [row for row in rows if row.technique_id == identity.technique_id]
        if len(rows) < self.policy.minimum_scores:
            raise AgentContractError(
                "insufficient resolved prequential scores for historical evidence"
            )
        if domain_count < self.policy.minimum_domains:
            raise AgentContractError("insufficient domain coverage for historical evidence")
        if independent_runs < self.policy.minimum_independent_runs:
            raise AgentContractError("insufficient independent runs for historical evidence")
        aggregate = self.ledger.aggregate(
            identity.expert_id,
            available_before=available_before,
            benchmark_id=benchmark_id,
            target_window_fingerprint=target_window_fingerprint,
        )
        metrics = {key: value for key, value in aggregate.items() if key != "count"}
        if calibration_ece is not None:
            metrics["calibration_ece"] = probability("calibration_ece", calibration_ece)
        evidence = tuple(
            sorted(
                {
                    *provenance_ids,
                    *(row.forecast_fingerprint for row in rows),
                }
            )
        )
        return HistoricalEvaluation(
            technique_id=identity.technique_id,
            as_of_year=as_of_year,
            knowledge_year=knowledge_year,
            data_cutoff_year=data_cutoff_year,
            benchmark_id=benchmark_id,
            target_window_fingerprint=target_window_fingerprint,
            folds=len(rows),
            series_count=len({row.target_id for row in rows}),
            domain_count=domain_count,
            independent_runs=independent_runs,
            metrics=metrics,
            leakage_audited=True,
            temporal_custody_verified=True,
            provenance_ids=evidence,
            calibration_checked=calibration_checked,
            metadata={
                "expert_id": identity.expert_id,
                "expert_fingerprint": identity.fingerprint,
                "score_ledger_fingerprint": self.ledger.fingerprint,
                "prequential": True,
                "available_before": available_before,
            },
        )


class FunctionalForecastExpert:
    """Adapter existing model families without inheritance coupling."""

    def __init__(
        self,
        identity: ExpertIdentity,
        forecast_function: Callable[[ForecastRequest], PredictiveDistribution],
        *,
        diagnostics_function: Callable[[ForecastRequest], Mapping[str, Any]] | None = None,
    ) -> None:
        self._identity = identity
        self._forecast_function = forecast_function
        self._diagnostics_function = diagnostics_function

    @property
    def identity(self) -> ExpertIdentity:
        return self._identity

    def forecast(self, request: ForecastRequest) -> ForecastEnvelope:
        distribution = self._forecast_function(request)
        if not isinstance(distribution, PredictiveDistribution):
            raise TypeError("forecast_function must return PredictiveDistribution")
        if distribution.target_kind is not request.target.kind:
            raise AgentContractError("adapter emitted distribution for wrong target kind")
        diagnostics = (
            self._diagnostics_function(request)
            if self._diagnostics_function is not None
            else {}
        )
        forecast_id = stable_id(
            "expert-forecast",
            {
                "request": request.fingerprint,
                "expert": self.identity.fingerprint,
                "distribution": distribution.fingerprint,
            },
            length=32,
        )
        return ForecastEnvelope(
            forecast_id=forecast_id,
            request_fingerprint=request.fingerprint,
            target_id=request.target.target_id,
            expert=self.identity,
            issued_at=request.issued_at,
            information_cutoff=request.information_cutoff,
            distribution=distribution,
            evidence_ids=request.provenance_ids,
            diagnostics=diagnostics,
        )
