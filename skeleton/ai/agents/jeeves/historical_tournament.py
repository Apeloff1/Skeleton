"""Champion–challenger tournament evaluation for Jeeves historical models.

A single candidate-vs-incumbent promotion gate is sufficient for activation, but
model development needs a broader comparison surface. This module evaluates many
challengers over the exact same immutable holdout suite/window, reuses the
promotion policy for every pair, computes per-domain deltas, and exposes a
Pareto frontier without turning the tournament into an activation mechanism.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalEvaluationError,
    HistoricalPromotionGate,
    HoldoutEvaluation,
    HoldoutWindow,
    PromotionDecision,
    PromotionPolicy,
)
from skeleton.jeeves.historical_models import BenchmarkDomain, HistoricalModelRegistry, ModelIdentity, canonical_fingerprint


class HistoricalTournamentError(HistoricalEvaluationError):
    code = "JVS.HISTORICAL_TOURNAMENT"
    http_status = 422


@dataclass(frozen=True, slots=True)
class DomainDelta:
    domain: BenchmarkDomain
    challenger_score: float
    incumbent_score: float
    delta: float


@dataclass(frozen=True, slots=True)
class ChallengerResult:
    model: ModelIdentity
    evaluation: HoldoutEvaluation
    decision: PromotionDecision
    aggregate_delta: float
    domain_deltas: tuple[DomainDelta, ...]
    dominates_incumbent: bool

    @property
    def promotable(self) -> bool:
        return self.decision.promotable


@dataclass(frozen=True, slots=True)
class TournamentReport:
    incumbent: ModelIdentity
    incumbent_evaluation: HoldoutEvaluation
    challengers: tuple[ChallengerResult, ...]
    pareto_frontier: tuple[ModelIdentity, ...]
    skipped_models: tuple[ModelIdentity, ...]
    suite_fingerprint: str
    policy_fingerprint: str
    report_fingerprint: str

    @property
    def promotable_challengers(self) -> tuple[ChallengerResult, ...]:
        return tuple(result for result in self.challengers if result.promotable)


class HistoricalChallengerTournament:
    """Evaluate a bounded explicit challenger set against one incumbent."""

    def __init__(
        self,
        *,
        registry: HistoricalModelRegistry,
        suite: BenchmarkSuite,
        window: HoldoutWindow,
        policy: PromotionPolicy | None = None,
    ) -> None:
        if not isinstance(registry, HistoricalModelRegistry):
            raise HistoricalTournamentError("registry must be HistoricalModelRegistry", context={"reason": "invalid_registry"})
        if not isinstance(suite, BenchmarkSuite):
            raise HistoricalTournamentError("suite must be BenchmarkSuite", context={"reason": "invalid_suite"})
        if not isinstance(window, HoldoutWindow):
            raise HistoricalTournamentError("window must be HoldoutWindow", context={"reason": "invalid_window"})
        if policy is None:
            policy = PromotionPolicy()
        if not isinstance(policy, PromotionPolicy):
            raise HistoricalTournamentError("policy must be PromotionPolicy", context={"reason": "invalid_policy"})
        self.registry = registry
        self.suite = suite
        self.window = window
        self.policy = policy
        self.gate = HistoricalPromotionGate(
            registry=registry,
            suite=suite,
            window=window,
            policy=policy,
        )

    def run(
        self,
        *,
        incumbent: ModelIdentity,
        challengers: Iterable[ModelIdentity],
    ) -> TournamentReport:
        if not isinstance(incumbent, ModelIdentity):
            raise HistoricalTournamentError("incumbent must be ModelIdentity", context={"reason": "invalid_incumbent"})
        challenger_tuple = tuple(sorted(set(challengers)))
        if any(not isinstance(model, ModelIdentity) for model in challenger_tuple):
            raise HistoricalTournamentError(
                "challengers must contain ModelIdentity values",
                context={"reason": "invalid_challenger"},
            )
        challenger_tuple = tuple(model for model in challenger_tuple if model != incumbent)
        if not challenger_tuple:
            raise HistoricalTournamentError(
                "at least one challenger distinct from incumbent is required",
                context={"reason": "empty_challengers"},
            )
        try:
            incumbent_eval = self.gate.evaluate(incumbent)
        except HistoricalEvaluationError as exc:
            raise HistoricalTournamentError(
                "incumbent lacks evaluable holdout evidence",
                context={"reason": "incumbent_not_evaluable", "model": incumbent.key},
                cause=exc,
            ) from exc
        if incumbent_eval.missing_required_domains:
            raise HistoricalTournamentError(
                "incumbent is missing required tournament domains",
                context={
                    "reason": "incumbent_missing_required_domain",
                    "model": incumbent.key,
                    "domains": [domain.value for domain in incumbent_eval.missing_required_domains],
                },
            )

        results: list[ChallengerResult] = []
        skipped: list[ModelIdentity] = []
        evaluations: dict[ModelIdentity, HoldoutEvaluation] = {incumbent: incumbent_eval}
        for model in challenger_tuple:
            try:
                evaluation = self.gate.evaluate(model)
                if evaluation.missing_required_domains:
                    skipped.append(model)
                    continue
                decision = self.gate.decide(candidate=model, incumbent=incumbent)
            except HistoricalEvaluationError:
                skipped.append(model)
                continue
            evaluations[model] = evaluation
            domain_deltas = self._domain_deltas(evaluation, incumbent_eval)
            dominates = bool(domain_deltas) and all(item.delta >= 0.0 for item in domain_deltas) and any(
                item.delta > 0.0 for item in domain_deltas
            )
            results.append(
                ChallengerResult(
                    model=model,
                    evaluation=evaluation,
                    decision=decision,
                    aggregate_delta=evaluation.score - incumbent_eval.score,
                    domain_deltas=domain_deltas,
                    dominates_incumbent=dominates,
                )
            )

        if not results:
            raise HistoricalTournamentError(
                "no challenger has complete evaluable holdout evidence",
                context={"reason": "no_evaluable_challengers"},
            )
        ordered = tuple(
            sorted(
                results,
                key=lambda item: (
                    not item.promotable,
                    -item.aggregate_delta,
                    -item.evaluation.score,
                    -item.evaluation.samples,
                    item.model.key,
                ),
            )
        )
        frontier = self._pareto_frontier(evaluations)
        payload = {
            "incumbent": incumbent.key,
            "incumbent_evidence": incumbent_eval.evidence_fingerprint,
            "challengers": [
                {
                    "model": item.model.key,
                    "evidence": item.evaluation.evidence_fingerprint,
                    "decision": item.decision.decision_fingerprint,
                    "delta": item.aggregate_delta,
                    "promotable": item.promotable,
                    "dominates": item.dominates_incumbent,
                }
                for item in ordered
            ],
            "frontier": [model.key for model in frontier],
            "skipped": [model.key for model in sorted(skipped)],
            "suite": self.suite.fingerprint,
            "policy": self.policy.fingerprint,
            "window": [self.window.start_at, self.window.end_at],
        }
        return TournamentReport(
            incumbent=incumbent,
            incumbent_evaluation=incumbent_eval,
            challengers=ordered,
            pareto_frontier=frontier,
            skipped_models=tuple(sorted(skipped)),
            suite_fingerprint=self.suite.fingerprint,
            policy_fingerprint=self.policy.fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def _domain_deltas(
        self,
        challenger: HoldoutEvaluation,
        incumbent: HoldoutEvaluation,
    ) -> tuple[DomainDelta, ...]:
        deltas: list[DomainDelta] = []
        for domain in sorted(self.suite.required_domains, key=lambda item: item.value):
            challenger_domain = challenger.domain(domain)
            incumbent_domain = incumbent.domain(domain)
            if challenger_domain is None or incumbent_domain is None:
                continue
            deltas.append(
                DomainDelta(
                    domain=domain,
                    challenger_score=challenger_domain.score,
                    incumbent_score=incumbent_domain.score,
                    delta=challenger_domain.score - incumbent_domain.score,
                )
            )
        return tuple(deltas)

    def _pareto_frontier(
        self,
        evaluations: dict[ModelIdentity, HoldoutEvaluation],
    ) -> tuple[ModelIdentity, ...]:
        complete = {
            model: evaluation
            for model, evaluation in evaluations.items()
            if not evaluation.missing_required_domains
            and all(evaluation.domain(domain) is not None for domain in self.suite.required_domains)
        }
        frontier: list[ModelIdentity] = []
        for model, evaluation in complete.items():
            dominated = False
            for other_model, other in complete.items():
                if other_model == model:
                    continue
                comparisons = [
                    (
                        other.domain(domain).score,  # type: ignore[union-attr]
                        evaluation.domain(domain).score,  # type: ignore[union-attr]
                    )
                    for domain in self.suite.required_domains
                ]
                if comparisons and all(other_score >= score for other_score, score in comparisons) and any(
                    other_score > score for other_score, score in comparisons
                ):
                    dominated = True
                    break
            if not dominated:
                frontier.append(model)
        return tuple(sorted(frontier))


def summarize_tournament(report: TournamentReport) -> dict[str, object]:
    return {
        "incumbent": report.incumbent.key,
        "incumbent_score": report.incumbent_evaluation.score,
        "promotable_challengers": [item.model.key for item in report.promotable_challengers],
        "pareto_frontier": [model.key for model in report.pareto_frontier],
        "skipped_models": [model.key for model in report.skipped_models],
        "suite_fingerprint": report.suite_fingerprint,
        "policy_fingerprint": report.policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "challengers": [
            {
                "model": item.model.key,
                "score": item.evaluation.score,
                "aggregate_delta": item.aggregate_delta,
                "promotable": item.promotable,
                "dominates_incumbent": item.dominates_incumbent,
                "reasons": list(item.decision.reasons),
                "domain_deltas": [
                    {
                        "domain": delta.domain.value,
                        "challenger_score": delta.challenger_score,
                        "incumbent_score": delta.incumbent_score,
                        "delta": delta.delta,
                    }
                    for delta in item.domain_deltas
                ],
            }
            for item in report.challengers
        ],
    }