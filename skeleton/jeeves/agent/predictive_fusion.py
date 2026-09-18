"""Reliability-aware predictive fusion for Jeeves.

Signals from memory sequences, semantic lenses, games, causal models, and base
rates are not independent votes. This module combines compatible binary
forecasts while discounting correlated sources, learning source reliability,
preserving disagreement, and never converting prediction into evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Sequence

from .associative_memory import SequencePrediction
from .lens_hypergraph import LensHyperedge
from .semantic_prediction import SemanticForecast
from .types import AgentContractError, finite_number, json_safe, positive_int, probability, stable_fingerprint, stable_id


class PredictiveSource(str, Enum):
    MEMORY_SEQUENCE = "memory_sequence"
    SEMANTIC_LENS = "semantic_lens"
    SEMANTIC_HYPEREDGE = "semantic_hyperedge"
    CAUSAL_MODEL = "causal_model"
    GAME_MODEL = "game_model"
    EMPIRICAL_BASE_RATE = "empirical_base_rate"
    HUMAN_PRIOR = "human_prior"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ReliabilityPosterior:
    successes: float = 1.0
    failures: float = 1.0

    def __post_init__(self) -> None:
        s = finite_number("successes", self.successes)
        f = finite_number("failures", self.failures)
        if s <= 0 or f <= 0:
            raise AgentContractError("beta reliability parameters must be positive")
        object.__setattr__(self, "successes", s)
        object.__setattr__(self, "failures", f)

    @property
    def mean(self) -> float:
        return self.successes / (self.successes + self.failures)

    @property
    def effective_samples(self) -> float:
        return max(0.0, self.successes + self.failures - 2.0)

    def update(self, success: bool, *, weight: float = 1.0) -> "ReliabilityPosterior":
        w = finite_number("weight", weight)
        if w <= 0:
            raise AgentContractError("reliability update weight must be positive")
        return ReliabilityPosterior(
            self.successes + (w if success else 0.0),
            self.failures + (0.0 if success else w),
        )


@dataclass(frozen=True, slots=True)
class PredictiveSignal:
    signal_id: str
    proposition: str
    probability: float
    source: PredictiveSource
    source_key: str
    independence_group: str
    base_weight: float = 0.5
    ambiguity: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.signal_id).strip() or not str(self.proposition).strip():
            raise AgentContractError("predictive signal requires id and proposition")
        object.__setattr__(self, "probability", probability("signal probability", self.probability))
        if not isinstance(self.source, PredictiveSource):
            object.__setattr__(self, "source", PredictiveSource(str(self.source)))
        object.__setattr__(self, "source_key", str(self.source_key).strip().casefold())
        object.__setattr__(self, "independence_group", str(self.independence_group).strip().casefold())
        if not self.source_key or not self.independence_group:
            raise AgentContractError("source_key and independence_group are required")
        object.__setattr__(self, "base_weight", probability("base_weight", self.base_weight))
        object.__setattr__(self, "ambiguity", probability("ambiguity", self.ambiguity))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "proposition": self.proposition,
            "probability": self.probability,
            "source": self.source.value,
            "source_key": self.source_key,
            "group": self.independence_group,
            "weight": self.base_weight,
            "ambiguity": self.ambiguity,
            "evidence": self.evidence_ids,
        })


@dataclass(frozen=True, slots=True)
class FusionPolicy:
    maximum_signal_weight: float = 0.70
    minimum_signal_weight: float = 0.01
    ambiguity_penalty: float = 0.65
    duplicate_group_penalty: float = 0.55
    prior_probability: float = 0.50
    prior_weight: float = 0.20
    minimum_probability: float = 0.01
    maximum_probability: float = 0.99
    minimum_independence_groups: int = 2
    high_disagreement_threshold: float = 0.25

    def __post_init__(self) -> None:
        for name in (
            "maximum_signal_weight", "minimum_signal_weight", "ambiguity_penalty",
            "duplicate_group_penalty", "prior_probability", "prior_weight",
            "minimum_probability", "maximum_probability", "high_disagreement_threshold",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(
            self, "minimum_independence_groups",
            positive_int("minimum_independence_groups", self.minimum_independence_groups, maximum=1000),
        )
        if self.minimum_probability >= self.maximum_probability:
            raise AgentContractError("probability bounds are invalid")


@dataclass(frozen=True, slots=True)
class SignalAttribution:
    signal_id: str
    source_key: str
    independence_group: str
    probability: float
    reliability: float
    effective_weight: float
    log_odds_contribution: float


@dataclass(frozen=True, slots=True)
class FusedPrediction:
    proposition: str
    probability: float
    robust_lower: float
    robust_upper: float
    disagreement: float
    entropy_bits: float
    epistemic_dispersion: float
    source_count: int
    independence_groups: tuple[str, ...]
    underidentified: bool
    attributions: tuple[SignalAttribution, ...]
    evidence_ids: tuple[str, ...]
    fingerprint: str


class PredictiveFusionEngine:
    def __init__(self, *, policy: FusionPolicy | None = None) -> None:
        self.policy = policy or FusionPolicy()
        self._reliability: dict[str, ReliabilityPosterior] = {}

    def reliability(self, source_key: str) -> ReliabilityPosterior:
        key = str(source_key).strip().casefold()
        return self._reliability.get(key, ReliabilityPosterior())

    def record_outcome(
        self,
        source_key: str,
        *,
        predicted_probability: float,
        outcome: bool,
        weight: float = 1.0,
    ) -> ReliabilityPosterior:
        p = probability("predicted_probability", predicted_probability)
        w = finite_number("weight", weight)
        if w <= 0:
            raise AgentContractError("outcome weight must be positive")
        if not isinstance(outcome, bool):
            raise AgentContractError("outcome must be bool")
        # Reliability is correctness of direction, not a substitute for calibration.
        # p == .5 is neutral and earns half credit rather than a forced success/failure.
        directional_success = (p > 0.5 and outcome) or (p < 0.5 and not outcome)
        key = str(source_key).strip().casefold()
        posterior = self.reliability(key)
        if abs(p - 0.5) < 1e-12:
            updated = ReliabilityPosterior(
                posterior.successes + 0.5 * w,
                posterior.failures + 0.5 * w,
            )
        else:
            updated = posterior.update(directional_success, weight=w)
        self._reliability[key] = updated
        return updated

    @staticmethod
    def _logit(p: float) -> float:
        x = min(1.0 - 1e-9, max(1e-9, p))
        return math.log(x / (1.0 - x))

    @staticmethod
    def _logistic(x: float) -> float:
        if x >= 0:
            e = math.exp(-x)
            return 1.0 / (1.0 + e)
        e = math.exp(x)
        return e / (1.0 + e)

    def fuse(self, proposition: str, signals: Sequence[PredictiveSignal]) -> FusedPrediction:
        usable = [signal for signal in signals if signal.proposition == proposition]
        if not usable:
            raise AgentContractError("fusion requires compatible signals for proposition")
        group_counts: dict[str, int] = {}
        for signal in usable:
            group_counts[signal.independence_group] = group_counts.get(signal.independence_group, 0) + 1

        weighted_log_odds = self.policy.prior_weight * self._logit(self.policy.prior_probability)
        total_weight = self.policy.prior_weight
        attributions: list[SignalAttribution] = []
        probabilities: list[float] = []
        evidence_ids: set[str] = set()
        for signal in usable:
            posterior = self.reliability(signal.source_key)
            reliability = posterior.mean
            duplicate_factor = 1.0 / (1.0 + self.policy.duplicate_group_penalty * (group_counts[signal.independence_group] - 1))
            ambiguity_factor = max(0.0, 1.0 - self.policy.ambiguity_penalty * signal.ambiguity)
            effective = signal.base_weight * reliability * duplicate_factor * ambiguity_factor
            effective = min(self.policy.maximum_signal_weight, max(self.policy.minimum_signal_weight, effective))
            contribution = effective * self._logit(signal.probability)
            weighted_log_odds += contribution
            total_weight += effective
            probabilities.append(signal.probability)
            evidence_ids.update(signal.evidence_ids)
            attributions.append(SignalAttribution(
                signal.signal_id, signal.source_key, signal.independence_group,
                signal.probability, reliability, effective, contribution,
            ))
        pooled = self._logistic(weighted_log_odds / max(total_weight, 1e-12))
        pooled = min(self.policy.maximum_probability, max(self.policy.minimum_probability, pooled))
        mean = sum(probabilities) / len(probabilities)
        variance = sum((p - mean) ** 2 for p in probabilities) / len(probabilities)
        dispersion = min(1.0, math.sqrt(variance) * 2.0)
        disagreement = max(probabilities) - min(probabilities)
        robust_lower = min(probabilities + [self.policy.prior_probability])
        robust_upper = max(probabilities + [self.policy.prior_probability])
        entropy = 0.0 if pooled in (0.0, 1.0) else -pooled * math.log2(pooled) - (1.0 - pooled) * math.log2(1.0 - pooled)
        groups = tuple(sorted(group_counts))
        underidentified = len(groups) < self.policy.minimum_independence_groups or disagreement >= self.policy.high_disagreement_threshold
        fp = stable_fingerprint({
            "proposition": proposition,
            "signals": sorted(signal.fingerprint for signal in usable),
            "probability": pooled,
            "lower": robust_lower,
            "upper": robust_upper,
            "groups": groups,
            "reliability": {key: self.reliability(key).mean for key in sorted({s.source_key for s in usable})},
        })
        return FusedPrediction(
            proposition=proposition,
            probability=pooled,
            robust_lower=robust_lower,
            robust_upper=robust_upper,
            disagreement=disagreement,
            entropy_bits=entropy,
            epistemic_dispersion=dispersion,
            source_count=len(usable),
            independence_groups=groups,
            underidentified=underidentified,
            attributions=tuple(sorted(attributions, key=lambda x: (-x.effective_weight, x.signal_id))),
            evidence_ids=tuple(sorted(evidence_ids)),
            fingerprint=fp,
        )

    def semantic_signal(self, forecast: SemanticForecast, *, weight: float = 0.45) -> PredictiveSignal:
        return PredictiveSignal(
            signal_id=forecast.forecast_id,
            proposition=forecast.proposition,
            probability=forecast.probability,
            source=PredictiveSource.SEMANTIC_LENS,
            source_key="semantic:" + "+".join(forecast.source_lens_keys or ("unknown",)),
            independence_group="semantic:" + (forecast.calibration_group or "generic"),
            base_weight=weight,
            ambiguity=forecast.ambiguity,
            evidence_ids=forecast.evidence_ids,
            metadata={"is_evidence": False, "forecast_fingerprint": forecast.fingerprint},
        )

    def hyperedge_signal(self, edge: LensHyperedge, proposition: str, *, weight: float = 0.35) -> PredictiveSignal:
        # Hyperedge confidence is interpretive confidence, so shrink aggressively toward .5.
        signed = edge.confidence - 0.5
        p = 0.5 + signed * max(0.0, 1.0 - edge.ambiguity) * 0.60
        if edge.unresolved:
            p = 0.5 + (p - 0.5) * 0.35
        return PredictiveSignal(
            signal_id=stable_id("hyperedge-signal", {"edge": edge.fingerprint, "proposition": proposition}, length=28),
            proposition=proposition,
            probability=p,
            source=PredictiveSource.SEMANTIC_HYPEREDGE,
            source_key="hyperedge:" + edge.edge_id,
            independence_group="semantic-hypergraph:" + edge.kind.value,
            base_weight=weight,
            ambiguity=edge.ambiguity,
            evidence_ids=edge.evidence_ids,
            metadata={"is_evidence": False, "edge": edge.edge_id, "unresolved": edge.unresolved},
        )

    def sequence_signals(
        self,
        prediction: SequencePrediction,
        *,
        proposition_prefix: str = "next-card:",
        weight: float = 0.55,
    ) -> tuple[PredictiveSignal, ...]:
        result: list[PredictiveSignal] = []
        for card_id, p in prediction.candidates:
            proposition = f"{proposition_prefix}{card_id}"
            result.append(PredictiveSignal(
                signal_id=stable_id("sequence-signal", {"prediction": prediction.fingerprint, "card": card_id}, length=28),
                proposition=proposition,
                probability=p,
                source=PredictiveSource.MEMORY_SEQUENCE,
                source_key="memory-sequence:" + prediction.namespace_key,
                independence_group="memory-sequence:" + prediction.namespace_key,
                base_weight=weight,
                ambiguity=min(1.0, prediction.entropy_bits / max(1.0, math.log2(max(2, len(prediction.candidates))))),
                metadata={"evidence_count": prediction.evidence_count, "prefix": list(prediction.prefix)},
            ))
        return tuple(result)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({key: (value.successes, value.failures) for key, value in sorted(self._reliability.items())})