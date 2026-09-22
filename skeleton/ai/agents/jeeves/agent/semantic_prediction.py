"""Prediction layer for semantic-lens hypotheses.

Semantic lenses are useful only if they can eventually be wrong.  This module
turns supported lens readings into explicitly provisional forecasts, records
outcomes, and evaluates calibration with proper scoring rules.

The model is intentionally conservative:
* interpretations become forecast *features/priors*, never observations;
* ambiguity shrinks probabilities toward 0.5;
* counter-readings remain separate competing forecasts;
* forecasts carry falsifiers and a calibration group;
* only an observed outcome can resolve a forecast;
* resolved forecasts can be scored, but scoring does not retroactively turn the
  semantic reading into factual evidence.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .advanced_uncertainty import ForecastCase, ProperScoring
from .semantic_frontier import LensInteraction, SemanticComposition
from .semantic_lenses import ReadingStatus, SemanticFinding
from .types import AgentContractError, bounded_text, finite_number, json_safe, positive_int, probability, stable_fingerprint, stable_id


class PredictionStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class SemanticForecast:
    forecast_id: str
    proposition: str
    probability: float
    created_at: float
    horizon: str
    source_finding_ids: tuple[str, ...] = ()
    source_interaction_ids: tuple[str, ...] = ()
    source_lens_keys: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    falsifiers: tuple[str, ...] = ()
    calibration_group: str = "semantic"
    ambiguity: float = 0.5
    epistemic_strength: float = 0.5
    status: PredictionStatus = PredictionStatus.OPEN
    outcome: bool | None = None
    resolved_at: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "forecast_id", str(self.forecast_id).strip())
        if not self.forecast_id:
            raise AgentContractError("forecast_id is required")
        object.__setattr__(self, "proposition", bounded_text("forecast proposition", self.proposition, maximum=8192))
        object.__setattr__(self, "probability", probability("forecast probability", self.probability))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("created_at must be non-negative")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "horizon", bounded_text("forecast horizon", self.horizon, maximum=512))
        object.__setattr__(self, "source_finding_ids", tuple(sorted({str(x) for x in self.source_finding_ids if str(x)})))
        object.__setattr__(self, "source_interaction_ids", tuple(sorted({str(x) for x in self.source_interaction_ids if str(x)})))
        object.__setattr__(self, "source_lens_keys", tuple(sorted({str(x).casefold() for x in self.source_lens_keys if str(x)})))
        object.__setattr__(self, "observation_ids", tuple(sorted({str(x) for x in self.observation_ids if str(x)})))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "falsifiers", tuple(str(x).strip() for x in self.falsifiers if str(x).strip()))
        object.__setattr__(self, "calibration_group", bounded_text("calibration_group", self.calibration_group, maximum=256))
        object.__setattr__(self, "ambiguity", probability("forecast ambiguity", self.ambiguity))
        object.__setattr__(self, "epistemic_strength", probability("epistemic_strength", self.epistemic_strength))
        if not isinstance(self.status, PredictionStatus):
            object.__setattr__(self, "status", PredictionStatus(str(self.status)))
        if self.status is PredictionStatus.RESOLVED and self.outcome is None:
            raise AgentContractError("resolved forecast requires outcome")
        if self.outcome is not None and not isinstance(self.outcome, bool):
            raise AgentContractError("forecast outcome must be boolean")
        if self.resolved_at is not None:
            resolved = finite_number("resolved_at", self.resolved_at)
            if resolved < created:
                raise AgentContractError("resolved_at predates forecast")
            object.__setattr__(self, "resolved_at", resolved)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "proposition": self.proposition,
                "probability": self.probability,
                "finding_ids": self.source_finding_ids,
                "interaction_ids": self.source_interaction_ids,
                "lens_keys": self.source_lens_keys,
                "observations": self.observation_ids,
                "evidence": self.evidence_ids,
                "falsifiers": self.falsifiers,
                "group": self.calibration_group,
                "status": self.status.value,
                "outcome": self.outcome,
            }
        )


@dataclass(frozen=True, slots=True)
class PredictionEvaluation:
    count: int
    brier: float
    log_score: float
    mean_probability: float
    empirical_rate: float
    calibration_gap: float
    by_group: Mapping[str, Mapping[str, float]]
    fingerprint: str


class SemanticPredictionLedger:
    """Bounded deterministic ledger for forecasts and observed resolutions."""

    def __init__(self, *, max_forecasts: int = 100_000, clock: Callable[[], float] = time.time) -> None:
        self.max_forecasts = positive_int("max_forecasts", max_forecasts, maximum=10_000_000)
        self._clock = clock
        self._forecasts: dict[str, SemanticForecast] = {}

    def add(self, forecast: SemanticForecast) -> SemanticForecast:
        if not isinstance(forecast, SemanticForecast):
            raise TypeError("forecast must be SemanticForecast")
        existing = self._forecasts.get(forecast.forecast_id)
        if existing is not None:
            if existing.fingerprint != forecast.fingerprint:
                raise AgentContractError(f"forecast id collision: {forecast.forecast_id}")
            return existing
        if len(self._forecasts) >= self.max_forecasts:
            self._evict()
        self._forecasts[forecast.forecast_id] = forecast
        return forecast

    def get(self, forecast_id: str) -> SemanticForecast | None:
        return self._forecasts.get(str(forecast_id))

    def resolve(self, forecast_id: str, *, outcome: bool, observed_at: float | None = None, observation_id: str | None = None) -> SemanticForecast:
        forecast = self._forecasts[str(forecast_id)]
        if forecast.status is not PredictionStatus.OPEN:
            raise AgentContractError("only open forecasts can be resolved")
        if not isinstance(outcome, bool):
            raise AgentContractError("outcome must be boolean")
        now = self._clock() if observed_at is None else finite_number("observed_at", observed_at)
        observation_ids = forecast.observation_ids
        if observation_id:
            observation_ids = tuple(sorted(set(observation_ids) | {str(observation_id)}))
        updated = replace(
            forecast,
            status=PredictionStatus.RESOLVED,
            outcome=outcome,
            resolved_at=now,
            observation_ids=observation_ids,
        )
        self._forecasts[forecast.forecast_id] = updated
        return updated

    def invalidate(self, forecast_id: str, *, reason: str) -> SemanticForecast:
        forecast = self._forecasts[str(forecast_id)]
        if forecast.status is PredictionStatus.RESOLVED:
            raise AgentContractError("resolved forecast cannot be invalidated")
        updated = replace(
            forecast,
            status=PredictionStatus.INVALIDATED,
            metadata={**dict(forecast.metadata), "invalidation_reason": bounded_text("reason", reason, maximum=2048)},
        )
        self._forecasts[forecast.forecast_id] = updated
        return updated

    def open(self) -> tuple[SemanticForecast, ...]:
        return tuple(sorted((item for item in self._forecasts.values() if item.status is PredictionStatus.OPEN), key=lambda item: (item.created_at, item.forecast_id)))

    def resolved(self) -> tuple[SemanticForecast, ...]:
        return tuple(sorted((item for item in self._forecasts.values() if item.status is PredictionStatus.RESOLVED), key=lambda item: (item.resolved_at or 0.0, item.forecast_id)))

    def evaluate(self, *, calibration_group: str | None = None) -> PredictionEvaluation:
        forecasts = [
            item for item in self.resolved()
            if item.outcome is not None and (calibration_group is None or item.calibration_group == calibration_group)
        ]
        if not forecasts:
            raise AgentContractError("prediction evaluation requires resolved forecasts")
        cases = [ForecastCase(item.probability, bool(item.outcome), group=item.calibration_group) for item in forecasts]
        brier = ProperScoring.brier(cases)
        log_score = ProperScoring.log_score(cases)
        mean_probability = sum(item.probability for item in forecasts) / len(forecasts)
        empirical_rate = sum(bool(item.outcome) for item in forecasts) / len(forecasts)
        groups: dict[str, dict[str, float]] = {}
        for group in sorted({item.calibration_group for item in forecasts}):
            subset = [item for item in forecasts if item.calibration_group == group]
            group_cases = [ForecastCase(item.probability, bool(item.outcome), group=group) for item in subset]
            mean_p = sum(item.probability for item in subset) / len(subset)
            rate = sum(bool(item.outcome) for item in subset) / len(subset)
            groups[group] = {
                "count": float(len(subset)),
                "brier": ProperScoring.brier(group_cases),
                "log_score": ProperScoring.log_score(group_cases),
                "mean_probability": mean_p,
                "empirical_rate": rate,
                "calibration_gap": abs(mean_p - rate),
            }
        fingerprint = stable_fingerprint(
            {
                "forecasts": [(item.forecast_id, item.probability, item.outcome) for item in forecasts],
                "brier": brier,
                "log_score": log_score,
                "groups": groups,
            }
        )
        return PredictionEvaluation(
            count=len(forecasts),
            brier=brier,
            log_score=log_score,
            mean_probability=mean_probability,
            empirical_rate=empirical_rate,
            calibration_gap=abs(mean_probability - empirical_rate),
            by_group=groups,
            fingerprint=fingerprint,
        )

    def _evict(self) -> None:
        candidates = [item for item in self._forecasts.values() if item.status is not PredictionStatus.OPEN]
        if not candidates:
            raise AgentContractError("prediction ledger full of unresolved forecasts")
        victim = min(candidates, key=lambda item: (item.resolved_at or item.created_at, item.created_at, item.forecast_id))
        self._forecasts.pop(victim.forecast_id, None)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint([(key, value.fingerprint) for key, value in sorted(self._forecasts.items())])


@dataclass(frozen=True, slots=True)
class PredictionPolicy:
    minimum_finding_confidence: float = 0.35
    base_shrinkage: float = 0.30
    ambiguity_shrinkage: float = 0.65
    contested_shrinkage: float = 0.35
    minimum_probability: float = 0.02
    maximum_probability: float = 0.98

    def __post_init__(self) -> None:
        for name in (
            "minimum_finding_confidence", "base_shrinkage", "ambiguity_shrinkage",
            "contested_shrinkage", "minimum_probability", "maximum_probability",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if self.minimum_probability >= self.maximum_probability:
            raise AgentContractError("minimum_probability must be below maximum_probability")


class SemanticPredictiveModel:
    """Convert semantic hypotheses into conservative, falsifiable forecasts."""

    def __init__(self, *, policy: PredictionPolicy | None = None, clock: Callable[[], float] = time.time) -> None:
        self.policy = policy or PredictionPolicy()
        self._clock = clock

    def _shrink(self, confidence: float, ambiguity: float, *, contested: bool) -> float:
        confidence = probability("confidence", confidence)
        ambiguity = probability("ambiguity", ambiguity)
        # Interpretive confidence is not calibrated event probability.  Map it to
        # an intentionally conservative forecast by shrinking toward indifference.
        distance = confidence - 0.5
        strength = 1.0 - self.policy.base_shrinkage
        strength *= max(0.0, 1.0 - self.policy.ambiguity_shrinkage * ambiguity)
        if contested:
            strength *= 1.0 - self.policy.contested_shrinkage
        p = 0.5 + distance * strength
        return min(self.policy.maximum_probability, max(self.policy.minimum_probability, p))

    def from_finding(self, finding: SemanticFinding, *, horizon: str = "next-relevant-observation") -> SemanticForecast | None:
        if finding.confidence < self.policy.minimum_finding_confidence or not finding.prediction.strip():
            return None
        contested = finding.status in {ReadingStatus.CONTESTED, ReadingStatus.FALSIFIED} or bool(finding.counterreading.strip())
        p = self._shrink(finding.confidence, finding.ambiguity, contested=contested)
        falsifiers = [f"Observe a relevant case where this prediction fails: {finding.prediction}"]
        if finding.counterreading.strip():
            falsifiers.append(f"Counter-reading better predicts the same observation: {finding.counterreading}")
        forecast_id = stable_id(
            "semantic-forecast",
            {
                "finding": finding.fingerprint,
                "prediction": finding.prediction,
                "horizon": horizon,
                "confidence": finding.confidence,
                "ambiguity": finding.ambiguity,
                "status": finding.status.value,
            },
            length=28,
        )
        return SemanticForecast(
            forecast_id=forecast_id,
            proposition=finding.prediction,
            probability=p,
            created_at=self._clock(),
            horizon=horizon,
            source_finding_ids=(finding.finding_id,),
            source_lens_keys=(finding.lens_key,),
            observation_ids=finding.observation_ids,
            evidence_ids=finding.evidence_ids,
            falsifiers=tuple(falsifiers),
            calibration_group=f"semantic:{finding.family.value}:{finding.lens_key}",
            ambiguity=finding.ambiguity,
            epistemic_strength=finding.confidence,
            metadata={
                "interpretive_source": True,
                "is_evidence": False,
                "status": finding.status.value,
                "source_fingerprint": finding.fingerprint,
            },
        )

    def from_interaction(self, interaction: LensInteraction, *, horizon: str = "next-discriminating-observation") -> SemanticForecast:
        p = self._shrink(interaction.confidence, interaction.ambiguity, contested=bool(interaction.counter_hypothesis))
        proposition = interaction.rule.predictive_effect
        forecast_id = stable_id(
            "semantic-forecast",
            {
                "interaction": interaction.fingerprint,
                "prediction": proposition,
                "horizon": horizon,
                "confidence": interaction.confidence,
                "ambiguity": interaction.ambiguity,
            },
            length=28,
        )
        return SemanticForecast(
            forecast_id=forecast_id,
            proposition=proposition,
            probability=p,
            created_at=self._clock(),
            horizon=horizon,
            source_interaction_ids=(interaction.interaction_id,),
            source_lens_keys=(interaction.rule.left_key, interaction.rule.right_key),
            observation_ids=interaction.observation_ids,
            evidence_ids=interaction.evidence_ids,
            falsifiers=(interaction.rule.question,),
            calibration_group=f"semantic-interaction:{interaction.rule.kind.value}",
            ambiguity=interaction.ambiguity,
            epistemic_strength=interaction.confidence,
            metadata={
                "interpretive_source": True,
                "is_evidence": False,
                "interaction_kind": interaction.rule.kind.value,
                "source_fingerprint": interaction.fingerprint,
            },
        )

    def propose(self, findings: Sequence[SemanticFinding], *, composition: SemanticComposition | None = None) -> tuple[SemanticForecast, ...]:
        forecasts: list[SemanticForecast] = []
        for finding in findings:
            forecast = self.from_finding(finding)
            if forecast is not None:
                forecasts.append(forecast)
        if composition is not None:
            forecasts.extend(self.from_interaction(interaction) for interaction in composition.interactions)
        # Deduplicate semantically identical forecast ids while preserving
        # competing propositions as separate entries.
        unique = {forecast.forecast_id: forecast for forecast in forecasts}
        return tuple(sorted(unique.values(), key=lambda item: item.forecast_id))


def log_odds_pool(probabilities: Sequence[tuple[float, float]]) -> float:
    """Explicit weighted log-odds pooling for compatible forecasts only.

    Callers must decide compatibility first.  The semantic layer never invokes
    this automatically for conflicting readings.
    """
    if not probabilities:
        raise AgentContractError("log_odds_pool requires probabilities")
    weighted = 0.0
    total = 0.0
    for p, weight in probabilities:
        p = probability("probability", p)
        w = finite_number("weight", weight)
        if w < 0:
            raise AgentContractError("pooling weight must be non-negative")
        clipped = min(1.0 - 1e-9, max(1e-9, p))
        weighted += w * math.log(clipped / (1.0 - clipped))
        total += w
    if total <= 0:
        raise AgentContractError("pooling weights sum to zero")
    x = weighted / total
    return 1.0 / (1.0 + math.exp(-x))
