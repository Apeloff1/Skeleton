"""Evidence-backed specialist portfolios for Jeeves historical models.

This module deliberately does *not* fabricate an ensemble score. Instead it
uses one common holdout suite/window to identify a strong general fallback and,
where the evidence margin is material, domain specialists that outperform the
fallback. The resulting plan is descriptive routing evidence; runtime provider
resolution remains the responsibility of the trusted provider catalog.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalEvaluationError,
    HistoricalPromotionGate,
    HoldoutEvaluation,
    HoldoutWindow,
    PromotionPolicy,
)
from skeleton.jeeves.historical_models import BenchmarkDomain, HistoricalModelRegistry, ModelIdentity, canonical_fingerprint


DEFAULT_MAX_PORTFOLIO_MODELS: Final = 4
MAX_PORTFOLIO_MODELS: Final = 16
DEFAULT_MIN_SPECIALIST_MARGIN: Final = 0.02


class HistoricalPortfolioError(HistoricalEvaluationError):
    code = "JVS.HISTORICAL_PORTFOLIO"
    http_status = 422


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalPortfolioError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_integer", "field": name},
        )
    return value


def _unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalPortfolioError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise HistoricalPortfolioError(
            f"{name} must be between 0 and 1",
            context={"reason": "out_of_range", "field": name},
        )
    return number


@dataclass(frozen=True, slots=True)
class PortfolioPolicy:
    max_models: int = DEFAULT_MAX_PORTFOLIO_MODELS
    min_specialist_margin: float = DEFAULT_MIN_SPECIALIST_MARGIN

    def __post_init__(self) -> None:
        max_models = _positive_int("max_models", self.max_models)
        if max_models > MAX_PORTFOLIO_MODELS:
            raise HistoricalPortfolioError(
                "max_models exceeds supported bound",
                context={"reason": "too_many_models", "maximum": MAX_PORTFOLIO_MODELS},
            )
        object.__setattr__(self, "max_models", max_models)
        object.__setattr__(self, "min_specialist_margin", _unit("min_specialist_margin", self.min_specialist_margin))

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "max_models": self.max_models,
                "min_specialist_margin": self.min_specialist_margin,
            }
        )


@dataclass(frozen=True, slots=True)
class ExpertAssignment:
    domain: BenchmarkDomain
    model: ModelIdentity
    domain_score: float
    fallback_score: float
    margin: float
    samples: int
    evidence_fingerprint: str
    is_specialist: bool


@dataclass(frozen=True, slots=True)
class ExpertPortfolio:
    fallback_model: ModelIdentity
    fallback_evaluation: HoldoutEvaluation
    assignments: tuple[ExpertAssignment, ...]
    models: tuple[ModelIdentity, ...]
    skipped_models: tuple[ModelIdentity, ...]
    suite_fingerprint: str
    policy_fingerprint: str
    portfolio_fingerprint: str

    def model_for(self, domain: BenchmarkDomain) -> ModelIdentity:
        if not isinstance(domain, BenchmarkDomain):
            raise HistoricalPortfolioError(
                "domain must be BenchmarkDomain",
                context={"reason": "invalid_domain"},
            )
        for assignment in self.assignments:
            if assignment.domain is domain:
                return assignment.model
        return self.fallback_model

    @property
    def specialist_domains(self) -> tuple[BenchmarkDomain, ...]:
        return tuple(assignment.domain for assignment in self.assignments if assignment.is_specialist)


class HistoricalExpertPortfolioBuilder:
    """Build a bounded specialist plan from one common holdout slice."""

    def __init__(
        self,
        *,
        registry: HistoricalModelRegistry,
        suite: BenchmarkSuite,
        window: HoldoutWindow,
        policy: PortfolioPolicy | None = None,
    ) -> None:
        if not isinstance(registry, HistoricalModelRegistry):
            raise HistoricalPortfolioError("registry must be HistoricalModelRegistry", context={"reason": "invalid_registry"})
        if not isinstance(suite, BenchmarkSuite):
            raise HistoricalPortfolioError("suite must be BenchmarkSuite", context={"reason": "invalid_suite"})
        if not isinstance(window, HoldoutWindow):
            raise HistoricalPortfolioError("window must be HoldoutWindow", context={"reason": "invalid_window"})
        if policy is None:
            policy = PortfolioPolicy()
        if not isinstance(policy, PortfolioPolicy):
            raise HistoricalPortfolioError("policy must be PortfolioPolicy", context={"reason": "invalid_policy"})
        self.registry = registry
        self.suite = suite
        self.window = window
        self.policy = policy
        self._gate = HistoricalPromotionGate(
            registry=registry,
            suite=suite,
            window=window,
            policy=PromotionPolicy(
                min_holdout_samples=1,
                min_coverage=0.0,
                min_promotion_margin=0.0,
                max_domain_regression=1.0,
                max_volatility=1.0,
                max_latest_drop=1.0,
            ),
        )

    def build(self, *, models: Iterable[ModelIdentity]) -> ExpertPortfolio:
        scope = tuple(sorted(set(models)))
        if not scope:
            raise HistoricalPortfolioError("models must not be empty", context={"reason": "empty_models"})
        if any(not isinstance(model, ModelIdentity) for model in scope):
            raise HistoricalPortfolioError(
                "models must contain ModelIdentity values",
                context={"reason": "invalid_model"},
            )

        evaluations: dict[ModelIdentity, HoldoutEvaluation] = {}
        skipped: list[ModelIdentity] = []
        for model in scope:
            try:
                evaluation = self._gate.evaluate(model)
            except HistoricalEvaluationError:
                skipped.append(model)
                continue
            if evaluation.missing_required_domains:
                skipped.append(model)
                continue
            evaluations[model] = evaluation
        if not evaluations:
            raise HistoricalPortfolioError(
                "no model has complete evaluable portfolio evidence",
                context={"reason": "no_evaluable_models"},
            )

        fallback = sorted(
            evaluations.values(),
            key=lambda item: (-item.score, -item.coverage, -item.samples, item.model.key),
        )[0]
        selected_models: set[ModelIdentity] = {fallback.model}
        assignments: list[ExpertAssignment] = []

        for domain in sorted(self.suite.domain_weights, key=lambda item: item.value):
            fallback_domain = fallback.domain(domain)
            if fallback_domain is None:
                continue
            candidates = []
            for evaluation in evaluations.values():
                result = evaluation.domain(domain)
                if result is not None:
                    candidates.append((result.score, result.samples, evaluation.model, evaluation.evidence_fingerprint))
            candidates.sort(key=lambda item: (-item[0], -item[1], item[2].key))
            best_score, best_samples, best_model, best_evidence = candidates[0]
            margin = best_score - fallback_domain.score
            use_specialist = (
                best_model != fallback.model
                and margin + 1e-12 >= self.policy.min_specialist_margin
                and (best_model in selected_models or len(selected_models) < self.policy.max_models)
            )
            if use_specialist:
                selected_models.add(best_model)
                chosen_model = best_model
                chosen_score = best_score
                chosen_samples = best_samples
                chosen_evidence = best_evidence
            else:
                chosen_model = fallback.model
                chosen_score = fallback_domain.score
                chosen_samples = fallback_domain.samples
                chosen_evidence = fallback.evidence_fingerprint
                margin = 0.0
            assignments.append(
                ExpertAssignment(
                    domain=domain,
                    model=chosen_model,
                    domain_score=chosen_score,
                    fallback_score=fallback_domain.score,
                    margin=margin,
                    samples=chosen_samples,
                    evidence_fingerprint=chosen_evidence,
                    is_specialist=chosen_model != fallback.model,
                )
            )

        assignment_tuple = tuple(assignments)
        models_tuple = tuple(sorted(selected_models))
        payload = {
            "fallback": fallback.model.key,
            "fallback_evidence": fallback.evidence_fingerprint,
            "assignments": [
                {
                    "domain": assignment.domain.value,
                    "model": assignment.model.key,
                    "score": assignment.domain_score,
                    "fallback_score": assignment.fallback_score,
                    "margin": assignment.margin,
                    "samples": assignment.samples,
                    "evidence": assignment.evidence_fingerprint,
                    "specialist": assignment.is_specialist,
                }
                for assignment in assignment_tuple
            ],
            "models": [model.key for model in models_tuple],
            "skipped": [model.key for model in sorted(skipped)],
            "suite": self.suite.fingerprint,
            "policy": self.policy.fingerprint,
            "window": [self.window.start_at, self.window.end_at],
        }
        return ExpertPortfolio(
            fallback_model=fallback.model,
            fallback_evaluation=fallback,
            assignments=assignment_tuple,
            models=models_tuple,
            skipped_models=tuple(sorted(skipped)),
            suite_fingerprint=self.suite.fingerprint,
            policy_fingerprint=self.policy.fingerprint,
            portfolio_fingerprint=canonical_fingerprint(payload),
        )


def summarize_portfolio(portfolio: ExpertPortfolio) -> dict[str, object]:
    return {
        "fallback_model": portfolio.fallback_model.key,
        "fallback_score": portfolio.fallback_evaluation.score,
        "models": [model.key for model in portfolio.models],
        "specialist_domains": [domain.value for domain in portfolio.specialist_domains],
        "skipped_models": [model.key for model in portfolio.skipped_models],
        "suite_fingerprint": portfolio.suite_fingerprint,
        "policy_fingerprint": portfolio.policy_fingerprint,
        "portfolio_fingerprint": portfolio.portfolio_fingerprint,
        "assignments": [
            {
                "domain": assignment.domain.value,
                "model": assignment.model.key,
                "domain_score": assignment.domain_score,
                "fallback_score": assignment.fallback_score,
                "margin": assignment.margin,
                "samples": assignment.samples,
                "is_specialist": assignment.is_specialist,
            }
            for assignment in portfolio.assignments
        ],
    }