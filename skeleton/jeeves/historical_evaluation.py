"""Holdout evaluation and promotion gates for Jeeves historical models.

The historical champion selector answers which recorded model looks strongest
under a workload policy. This module answers a different question: whether a
candidate has enough independent holdout evidence to replace an incumbent.

Promotion is deliberately conservative and deterministic. The gate works only
from immutable benchmark snapshots already admitted to the historical registry.
It requires an explicit benchmark suite, a holdout time window, sample floors,
coverage, bounded volatility, and regression tolerances. A candidate can win a
ranking and still be held back from promotion.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final

from skeleton.jeeves.historical_models import (
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelError,
    HistoricalModelRegistry,
    ModelIdentity,
    canonical_fingerprint,
)


MAX_SUITE_ITEMS: Final = 256
DEFAULT_MIN_HOLDOUT_SAMPLES: Final = 64
DEFAULT_MIN_COVERAGE: Final = 1.0
DEFAULT_MIN_PROMOTION_MARGIN: Final = 0.01
DEFAULT_MAX_DOMAIN_REGRESSION: Final = 0.02
DEFAULT_MAX_VOLATILITY: Final = 0.08
DEFAULT_MAX_LATEST_DROP: Final = 0.05


class HistoricalEvaluationError(HistoricalModelError):
    """Fail-closed evaluation or promotion contract error."""

    code = "JVS.HISTORICAL_EVALUATION"
    http_status = 422


class PromotionAction(str, Enum):
    PROMOTE = "promote"
    HOLD = "hold"


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalEvaluationError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalEvaluationError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise HistoricalEvaluationError(
            f"{name} must be between 0 and 1",
            context={"reason": "out_of_range", "field": name},
        )
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalEvaluationError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_integer", "field": name},
        )
    return value


def _text(name: str, value: object, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalEvaluationError(
            f"{name} must be a non-empty string",
            context={"reason": "invalid_text", "field": name},
        )
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalEvaluationError(
            f"{name} is too long",
            context={"reason": "too_long", "field": name, "max_chars": maximum},
        )
    return cleaned


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    """Immutable holdout suite contract.

    ``benchmark_keys`` contains exact ``benchmark_id@revision`` values. This
    prevents silently changing a benchmark implementation underneath a
    promotion decision.
    """

    suite_id: str
    revision: str
    benchmark_keys: frozenset[str]
    domain_weights: Mapping[BenchmarkDomain, float]
    required_domains: frozenset[BenchmarkDomain]

    def __post_init__(self) -> None:
        object.__setattr__(self, "suite_id", _text("suite_id", self.suite_id))
        object.__setattr__(self, "revision", _text("revision", self.revision))
        keys = frozenset(_text("benchmark_key", item) for item in self.benchmark_keys)
        if not keys:
            raise HistoricalEvaluationError(
                "benchmark suite must contain at least one benchmark",
                context={"reason": "empty_suite"},
            )
        if len(keys) > MAX_SUITE_ITEMS:
            raise HistoricalEvaluationError(
                "benchmark suite is too large",
                context={"reason": "suite_too_large", "max_items": MAX_SUITE_ITEMS},
            )
        object.__setattr__(self, "benchmark_keys", keys)

        clean_weights: dict[BenchmarkDomain, float] = {}
        for domain, weight in self.domain_weights.items():
            if not isinstance(domain, BenchmarkDomain):
                raise HistoricalEvaluationError(
                    "domain weight key must be BenchmarkDomain",
                    context={"reason": "invalid_domain"},
                )
            numeric = _finite(f"weight[{domain.value}]", weight)
            if numeric <= 0.0:
                raise HistoricalEvaluationError(
                    "domain weights must be positive",
                    context={"reason": "invalid_weight", "domain": domain.value},
                )
            clean_weights[domain] = numeric
        if not clean_weights:
            raise HistoricalEvaluationError(
                "suite domain weights must not be empty",
                context={"reason": "empty_weights"},
            )
        object.__setattr__(self, "domain_weights", clean_weights)

        required = frozenset(self.required_domains)
        if any(not isinstance(domain, BenchmarkDomain) for domain in required):
            raise HistoricalEvaluationError(
                "required_domains must contain BenchmarkDomain values",
                context={"reason": "invalid_domain"},
            )
        if not required.issubset(clean_weights):
            raise HistoricalEvaluationError(
                "required domains must have weights",
                context={"reason": "missing_weight"},
            )
        object.__setattr__(self, "required_domains", required)

    @property
    def key(self) -> str:
        return f"{self.suite_id}@{self.revision}"

    @property
    def normalized_weights(self) -> Mapping[BenchmarkDomain, float]:
        total = sum(self.domain_weights.values())
        return {domain: weight / total for domain, weight in self.domain_weights.items()}

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "suite": self.key,
                "benchmark_keys": sorted(self.benchmark_keys),
                "domain_weights": {
                    domain.value: weight
                    for domain, weight in sorted(self.domain_weights.items(), key=lambda item: item[0].value)
                },
                "required_domains": sorted(domain.value for domain in self.required_domains),
            }
        )


@dataclass(frozen=True, slots=True)
class HoldoutWindow:
    start_at: float
    end_at: float

    def __post_init__(self) -> None:
        start = _finite("start_at", self.start_at)
        end = _finite("end_at", self.end_at)
        if start < 0.0 or end < 0.0 or end <= start:
            raise HistoricalEvaluationError(
                "holdout window must have non-negative start and end > start",
                context={"reason": "invalid_window"},
            )
        object.__setattr__(self, "start_at", start)
        object.__setattr__(self, "end_at", end)

    def contains(self, timestamp: float) -> bool:
        return self.start_at <= timestamp <= self.end_at


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    min_holdout_samples: int = DEFAULT_MIN_HOLDOUT_SAMPLES
    min_coverage: float = DEFAULT_MIN_COVERAGE
    min_promotion_margin: float = DEFAULT_MIN_PROMOTION_MARGIN
    max_domain_regression: float = DEFAULT_MAX_DOMAIN_REGRESSION
    max_volatility: float = DEFAULT_MAX_VOLATILITY
    max_latest_drop: float = DEFAULT_MAX_LATEST_DROP

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_holdout_samples", _positive_int("min_holdout_samples", self.min_holdout_samples))
        object.__setattr__(self, "min_coverage", _unit("min_coverage", self.min_coverage))
        object.__setattr__(self, "max_volatility", _unit("max_volatility", self.max_volatility))
        object.__setattr__(self, "max_latest_drop", _unit("max_latest_drop", self.max_latest_drop))
        margin = _finite("min_promotion_margin", self.min_promotion_margin)
        if not 0.0 <= margin <= 1.0:
            raise HistoricalEvaluationError(
                "min_promotion_margin must be between 0 and 1",
                context={"reason": "invalid_margin"},
            )
        object.__setattr__(self, "min_promotion_margin", margin)
        regression = _finite("max_domain_regression", self.max_domain_regression)
        if not 0.0 <= regression <= 1.0:
            raise HistoricalEvaluationError(
                "max_domain_regression must be between 0 and 1",
                context={"reason": "invalid_regression"},
            )
        object.__setattr__(self, "max_domain_regression", regression)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "min_holdout_samples": self.min_holdout_samples,
                "min_coverage": self.min_coverage,
                "min_promotion_margin": self.min_promotion_margin,
                "max_domain_regression": self.max_domain_regression,
                "max_volatility": self.max_volatility,
                "max_latest_drop": self.max_latest_drop,
            }
        )


@dataclass(frozen=True, slots=True)
class HoldoutDomainResult:
    domain: BenchmarkDomain
    score: float
    samples: int
    volatility: float
    latest_score: float
    historical_score: float
    latest_drop: float
    snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HoldoutEvaluation:
    model: ModelIdentity
    suite_key: str
    window: HoldoutWindow
    score: float
    coverage: float
    samples: int
    max_volatility: float
    max_latest_drop: float
    domains: tuple[HoldoutDomainResult, ...]
    missing_required_domains: tuple[BenchmarkDomain, ...]
    evidence_fingerprint: str

    def domain(self, domain: BenchmarkDomain) -> HoldoutDomainResult | None:
        for item in self.domains:
            if item.domain is domain:
                return item
        return None


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    action: PromotionAction
    candidate: HoldoutEvaluation
    incumbent: HoldoutEvaluation | None
    reasons: tuple[str, ...]
    margin: float | None
    suite_fingerprint: str
    policy_fingerprint: str
    decision_fingerprint: str

    @property
    def promotable(self) -> bool:
        return self.action is PromotionAction.PROMOTE


class HistoricalPromotionGate:
    """Evaluate independent holdout evidence before incumbent replacement."""

    def __init__(
        self,
        *,
        registry: HistoricalModelRegistry,
        suite: BenchmarkSuite,
        window: HoldoutWindow,
        policy: PromotionPolicy | None = None,
    ) -> None:
        if not isinstance(registry, HistoricalModelRegistry):
            raise HistoricalEvaluationError(
                "registry must be HistoricalModelRegistry",
                context={"reason": "invalid_registry"},
            )
        if not isinstance(suite, BenchmarkSuite):
            raise HistoricalEvaluationError(
                "suite must be BenchmarkSuite",
                context={"reason": "invalid_suite"},
            )
        if not isinstance(window, HoldoutWindow):
            raise HistoricalEvaluationError(
                "window must be HoldoutWindow",
                context={"reason": "invalid_window"},
            )
        if policy is None:
            policy = PromotionPolicy()
        if not isinstance(policy, PromotionPolicy):
            raise HistoricalEvaluationError(
                "policy must be PromotionPolicy",
                context={"reason": "invalid_policy"},
            )
        self.registry = registry
        self.suite = suite
        self.window = window
        self.policy = policy

    def evaluate(self, model: ModelIdentity) -> HoldoutEvaluation:
        if not isinstance(model, ModelIdentity):
            raise HistoricalEvaluationError(
                "model must be ModelIdentity",
                context={"reason": "invalid_model"},
            )
        selected = [
            snapshot
            for snapshot in self.registry.snapshots_for(model)
            if snapshot.benchmark.key in self.suite.benchmark_keys
            and self.window.contains(snapshot.measured_at)
        ]
        if not selected:
            raise HistoricalEvaluationError(
                "model has no snapshots in the holdout suite and window",
                context={"reason": "no_holdout_evidence", "model": model.key},
            )

        by_domain: dict[BenchmarkDomain, list[BenchmarkSnapshot]] = defaultdict(list)
        for snapshot in selected:
            if snapshot.benchmark.domain in self.suite.domain_weights:
                by_domain[snapshot.benchmark.domain].append(snapshot)

        results: list[HoldoutDomainResult] = []
        missing_required: list[BenchmarkDomain] = []
        weighted_score = 0.0
        covered_weight = 0.0
        total_samples = 0

        for domain, domain_weight in self.suite.normalized_weights.items():
            snapshots = by_domain.get(domain, [])
            if not snapshots:
                if domain in self.suite.required_domains:
                    missing_required.append(domain)
                continue
            result = self._evaluate_domain(domain, snapshots)
            results.append(result)
            weighted_score += domain_weight * result.score
            covered_weight += domain_weight
            total_samples += result.samples

        score = weighted_score / covered_weight if covered_weight > 0.0 else 0.0
        evidence_ids = sorted(snapshot.snapshot_id for snapshot in selected)
        return HoldoutEvaluation(
            model=model,
            suite_key=self.suite.key,
            window=self.window,
            score=score,
            coverage=covered_weight,
            samples=total_samples,
            max_volatility=max((item.volatility for item in results), default=0.0),
            max_latest_drop=max((item.latest_drop for item in results), default=0.0),
            domains=tuple(sorted(results, key=lambda item: item.domain.value)),
            missing_required_domains=tuple(sorted(missing_required, key=lambda item: item.value)),
            evidence_fingerprint=canonical_fingerprint(evidence_ids),
        )

    def decide(
        self,
        *,
        candidate: ModelIdentity,
        incumbent: ModelIdentity | None = None,
    ) -> PromotionDecision:
        candidate_eval = self.evaluate(candidate)
        incumbent_eval = self.evaluate(incumbent) if incumbent is not None else None
        reasons: list[str] = []

        if candidate_eval.missing_required_domains:
            reasons.append("missing_required_domain")
        if candidate_eval.samples < self.policy.min_holdout_samples:
            reasons.append("insufficient_holdout_samples")
        if candidate_eval.coverage + 1e-12 < self.policy.min_coverage:
            reasons.append("insufficient_suite_coverage")
        if candidate_eval.max_volatility > self.policy.max_volatility + 1e-12:
            reasons.append("excessive_volatility")
        if candidate_eval.max_latest_drop > self.policy.max_latest_drop + 1e-12:
            reasons.append("recent_regression")

        margin: float | None = None
        if incumbent_eval is not None:
            margin = candidate_eval.score - incumbent_eval.score
            if margin + 1e-12 < self.policy.min_promotion_margin:
                reasons.append("insufficient_promotion_margin")
            for domain in self.suite.required_domains:
                candidate_domain = candidate_eval.domain(domain)
                incumbent_domain = incumbent_eval.domain(domain)
                if candidate_domain is None or incumbent_domain is None:
                    reasons.append("incomparable_required_domain")
                    continue
                if candidate_domain.score + self.policy.max_domain_regression + 1e-12 < incumbent_domain.score:
                    reasons.append(f"domain_regression:{domain.value}")

        action = PromotionAction.PROMOTE if not reasons else PromotionAction.HOLD
        normalized_reasons = tuple(sorted(set(reasons)))
        decision_payload = {
            "action": action.value,
            "candidate": candidate.key,
            "candidate_evidence": candidate_eval.evidence_fingerprint,
            "incumbent": incumbent.key if incumbent is not None else None,
            "incumbent_evidence": incumbent_eval.evidence_fingerprint if incumbent_eval is not None else None,
            "reasons": normalized_reasons,
            "margin": margin,
            "suite_fingerprint": self.suite.fingerprint,
            "policy_fingerprint": self.policy.fingerprint,
            "window": [self.window.start_at, self.window.end_at],
        }
        return PromotionDecision(
            action=action,
            candidate=candidate_eval,
            incumbent=incumbent_eval,
            reasons=normalized_reasons,
            margin=margin,
            suite_fingerprint=self.suite.fingerprint,
            policy_fingerprint=self.policy.fingerprint,
            decision_fingerprint=canonical_fingerprint(decision_payload),
        )

    @staticmethod
    def _evaluate_domain(
        domain: BenchmarkDomain,
        snapshots: list[BenchmarkSnapshot],
    ) -> HoldoutDomainResult:
        ordered = sorted(snapshots, key=lambda item: (item.measured_at, item.snapshot_id))
        weights = [float(item.sample_count) * item.benchmark.weight_hint for item in ordered]
        values = [item.normalized_score for item in ordered]
        total_weight = sum(weights)
        if total_weight <= 0.0:
            raise HistoricalEvaluationError(
                "holdout domain has zero effective weight",
                context={"reason": "zero_weight", "domain": domain.value},
            )
        score = sum(value * weight for value, weight in zip(values, weights, strict=True)) / total_weight
        variance = sum(
            weight * ((value - score) ** 2)
            for value, weight in zip(values, weights, strict=True)
        ) / total_weight
        volatility = math.sqrt(max(0.0, variance))
        latest_score = values[-1]
        if len(values) == 1:
            historical_score = latest_score
        else:
            prior_weights = weights[:-1]
            prior_values = values[:-1]
            prior_total = sum(prior_weights)
            historical_score = sum(
                value * weight for value, weight in zip(prior_values, prior_weights, strict=True)
            ) / prior_total
        latest_drop = max(0.0, historical_score - latest_score)
        return HoldoutDomainResult(
            domain=domain,
            score=score,
            samples=sum(item.sample_count for item in ordered),
            volatility=volatility,
            latest_score=latest_score,
            historical_score=historical_score,
            latest_drop=latest_drop,
            snapshot_ids=tuple(item.snapshot_id for item in ordered),
        )


def summarize_promotion(decision: PromotionDecision) -> Mapping[str, object]:
    """Return a compact JSON-safe promotion evidence envelope."""
    return {
        "action": decision.action.value,
        "promotable": decision.promotable,
        "candidate": decision.candidate.model.key,
        "candidate_score": decision.candidate.score,
        "candidate_coverage": decision.candidate.coverage,
        "candidate_samples": decision.candidate.samples,
        "candidate_max_volatility": decision.candidate.max_volatility,
        "candidate_max_latest_drop": decision.candidate.max_latest_drop,
        "incumbent": decision.incumbent.model.key if decision.incumbent is not None else None,
        "incumbent_score": decision.incumbent.score if decision.incumbent is not None else None,
        "margin": decision.margin,
        "reasons": list(decision.reasons),
        "suite_fingerprint": decision.suite_fingerprint,
        "policy_fingerprint": decision.policy_fingerprint,
        "decision_fingerprint": decision.decision_fingerprint,
    }