"""Leakage-resistant temporal backtesting for Jeeves historical model policies.

The production selector is intentionally evaluated as it would have existed at a
past decision boundary. Training snapshots are truncated at ``train_end`` and a
fresh temporary registry is scored with its clock fixed to that cutoff. Future
snapshots are never visible to ranking. The selected model is then evaluated on
an explicit forward holdout window using the same immutable benchmark suite used
by the promotion layer.

This module is descriptive infrastructure: it reports how a selection policy
would have behaved across historical folds. It does not mutate champion state or
activate providers.
"""

from __future__ import annotations

import math
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
from skeleton.jeeves.historical_models import (
    ChampionDecision,
    HistoricalModelError,
    HistoricalModelRegistry,
    ModelIdentity,
    SelectionPolicy,
    canonical_fingerprint,
)


MAX_BACKTEST_FOLDS: Final = 128
DEFAULT_MIN_FORWARD_COVERAGE: Final = 1.0
_EPSILON: Final = 1e-12


class HistoricalBacktestError(HistoricalEvaluationError):
    """Fail-closed temporal backtest contract violation."""

    code = "JVS.HISTORICAL_BACKTEST"
    http_status = 422


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalBacktestError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalBacktestError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise HistoricalBacktestError(
            f"{name} must be between 0 and 1",
            context={"reason": "out_of_range", "field": name},
        )
    return number


def _bounded_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalBacktestError(
            f"{name} must be a non-empty string",
            context={"reason": "invalid_text", "field": name},
        )
    cleaned = value.strip()
    if len(cleaned) > 160:
        raise HistoricalBacktestError(
            f"{name} is too long",
            context={"reason": "too_long", "field": name},
        )
    return cleaned


@dataclass(frozen=True, slots=True)
class BacktestFold:
    """One train-before-test temporal split."""

    fold_id: str
    train_end: float
    test_start: float
    test_end: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _bounded_id("fold_id", self.fold_id))
        train_end = _finite("train_end", self.train_end)
        test_start = _finite("test_start", self.test_start)
        test_end = _finite("test_end", self.test_end)
        if min(train_end, test_start, test_end) < 0.0:
            raise HistoricalBacktestError(
                "backtest timestamps must be non-negative",
                context={"reason": "invalid_fold_time", "fold_id": self.fold_id},
            )
        if test_start <= train_end:
            raise HistoricalBacktestError(
                "test_start must be strictly after train_end",
                context={"reason": "temporal_leakage", "fold_id": self.fold_id},
            )
        if test_end < test_start:
            raise HistoricalBacktestError(
                "test_end must be at or after test_start",
                context={"reason": "invalid_test_window", "fold_id": self.fold_id},
            )
        object.__setattr__(self, "train_end", train_end)
        object.__setattr__(self, "test_start", test_start)
        object.__setattr__(self, "test_end", test_end)

    @property
    def holdout_window(self) -> HoldoutWindow:
        # HoldoutWindow requires end > start. A single timestamp is represented
        # with the smallest deterministic positive interval used by this layer.
        end = self.test_end
        if end <= self.test_start:
            end = math.nextafter(self.test_start, math.inf)
        return HoldoutWindow(start_at=self.test_start, end_at=end)


@dataclass(frozen=True, slots=True)
class BacktestPlan:
    """Immutable rolling/expanding temporal evaluation plan."""

    plan_id: str
    revision: str
    folds: tuple[BacktestFold, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _bounded_id("plan_id", self.plan_id))
        object.__setattr__(self, "revision", _bounded_id("revision", self.revision))
        folds = tuple(self.folds)
        if not folds:
            raise HistoricalBacktestError("backtest plan must contain folds", context={"reason": "empty_plan"})
        if len(folds) > MAX_BACKTEST_FOLDS:
            raise HistoricalBacktestError(
                "backtest plan contains too many folds",
                context={"reason": "too_many_folds", "max_folds": MAX_BACKTEST_FOLDS},
            )
        if any(not isinstance(fold, BacktestFold) for fold in folds):
            raise HistoricalBacktestError(
                "folds must contain BacktestFold values",
                context={"reason": "invalid_fold"},
            )
        ids = [fold.fold_id for fold in folds]
        if len(ids) != len(set(ids)):
            raise HistoricalBacktestError(
                "backtest fold ids must be unique",
                context={"reason": "duplicate_fold_id"},
            )
        ordered = tuple(sorted(folds, key=lambda fold: (fold.train_end, fold.test_start, fold.fold_id)))
        if ordered != folds:
            raise HistoricalBacktestError(
                "backtest folds must be in chronological order",
                context={"reason": "unordered_folds"},
            )
        object.__setattr__(self, "folds", folds)

    @property
    def key(self) -> str:
        return f"{self.plan_id}@{self.revision}"

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "plan": self.key,
                "folds": [
                    {
                        "fold_id": fold.fold_id,
                        "train_end": fold.train_end,
                        "test_start": fold.test_start,
                        "test_end": fold.test_end,
                    }
                    for fold in self.folds
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class BacktestFoldResult:
    fold: BacktestFold
    ranking: ChampionDecision
    selected_holdout: HoldoutEvaluation
    oracle_model: ModelIdentity
    oracle_holdout: HoldoutEvaluation
    regret: float
    candidate_count: int
    train_snapshot_count: int
    train_evidence_fingerprint: str
    test_evidence_fingerprint: str

    @property
    def selected_model(self) -> ModelIdentity:
        return self.ranking.champion.model

    @property
    def selected_score(self) -> float:
        return self.selected_holdout.score

    @property
    def oracle_score(self) -> float:
        return self.oracle_holdout.score


@dataclass(frozen=True, slots=True)
class BacktestReport:
    plan_key: str
    plan_fingerprint: str
    policy_fingerprint: str
    suite_fingerprint: str
    min_forward_coverage: float
    folds: tuple[BacktestFoldResult, ...]
    mean_selected_score: float
    mean_oracle_score: float
    mean_regret: float
    worst_regret: float
    champion_stability: float
    unique_selected_models: tuple[ModelIdentity, ...]
    report_fingerprint: str

    @property
    def fold_count(self) -> int:
        return len(self.folds)


class TemporalHistoricalBacktester:
    """Replay a historical selection policy without allowing future leakage."""

    def __init__(
        self,
        *,
        registry: HistoricalModelRegistry,
        selection_policy: SelectionPolicy,
        suite: BenchmarkSuite,
        plan: BacktestPlan,
        min_forward_coverage: float = DEFAULT_MIN_FORWARD_COVERAGE,
    ) -> None:
        if not isinstance(registry, HistoricalModelRegistry):
            raise HistoricalBacktestError("registry must be HistoricalModelRegistry", context={"reason": "invalid_registry"})
        if not isinstance(selection_policy, SelectionPolicy):
            raise HistoricalBacktestError(
                "selection_policy must be SelectionPolicy",
                context={"reason": "invalid_policy"},
            )
        if not isinstance(suite, BenchmarkSuite):
            raise HistoricalBacktestError("suite must be BenchmarkSuite", context={"reason": "invalid_suite"})
        if not isinstance(plan, BacktestPlan):
            raise HistoricalBacktestError("plan must be BacktestPlan", context={"reason": "invalid_plan"})
        self.registry = registry
        self.selection_policy = selection_policy
        self.suite = suite
        self.plan = plan
        self.min_forward_coverage = _unit("min_forward_coverage", min_forward_coverage)

    def run(self, *, models: Iterable[ModelIdentity] | None = None) -> BacktestReport:
        scope = None if models is None else tuple(sorted(set(models)))
        if scope is not None and any(not isinstance(model, ModelIdentity) for model in scope):
            raise HistoricalBacktestError(
                "models must contain ModelIdentity values",
                context={"reason": "invalid_model"},
            )
        results = tuple(self._run_fold(fold, scope=scope) for fold in self.plan.folds)
        if not results:
            raise HistoricalBacktestError("backtest produced no results", context={"reason": "empty_report"})

        mean_selected = sum(item.selected_score for item in results) / len(results)
        mean_oracle = sum(item.oracle_score for item in results) / len(results)
        mean_regret = sum(item.regret for item in results) / len(results)
        worst_regret = max(item.regret for item in results)
        selections = tuple(item.selected_model for item in results)
        if len(selections) <= 1:
            stability = 1.0
        else:
            repeats = sum(1 for left, right in zip(selections, selections[1:]) if left == right)
            stability = repeats / (len(selections) - 1)
        unique = tuple(sorted(set(selections)))
        policy_fingerprint = canonical_fingerprint(HistoricalModelRegistry._policy_payload(self.selection_policy))
        payload = {
            "plan_fingerprint": self.plan.fingerprint,
            "policy_fingerprint": policy_fingerprint,
            "suite_fingerprint": self.suite.fingerprint,
            "min_forward_coverage": self.min_forward_coverage,
            "folds": [
                {
                    "fold_id": item.fold.fold_id,
                    "selected": item.selected_model.key,
                    "selected_score": item.selected_score,
                    "oracle": item.oracle_model.key,
                    "oracle_score": item.oracle_score,
                    "regret": item.regret,
                    "train_evidence": item.train_evidence_fingerprint,
                    "test_evidence": item.test_evidence_fingerprint,
                }
                for item in results
            ],
        }
        return BacktestReport(
            plan_key=self.plan.key,
            plan_fingerprint=self.plan.fingerprint,
            policy_fingerprint=policy_fingerprint,
            suite_fingerprint=self.suite.fingerprint,
            min_forward_coverage=self.min_forward_coverage,
            folds=results,
            mean_selected_score=mean_selected,
            mean_oracle_score=mean_oracle,
            mean_regret=mean_regret,
            worst_regret=worst_regret,
            champion_stability=stability,
            unique_selected_models=unique,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def _run_fold(
        self,
        fold: BacktestFold,
        *,
        scope: tuple[ModelIdentity, ...] | None,
    ) -> BacktestFoldResult:
        training = [snapshot for snapshot in self.registry.snapshots() if snapshot.measured_at <= fold.train_end]
        if not training:
            raise HistoricalBacktestError(
                "fold has no training snapshots",
                context={"reason": "no_training_evidence", "fold_id": fold.fold_id},
            )
        train_registry = HistoricalModelRegistry(
            clock=lambda cutoff=fold.train_end: cutoff,
            max_snapshots_per_benchmark=self.registry.max_snapshots_per_benchmark,
        )
        for snapshot in training:
            train_registry.ingest(snapshot)
        try:
            ranking = train_registry.select_champion(self.selection_policy, models=scope)
        except HistoricalModelError as exc:
            raise HistoricalBacktestError(
                "fold could not select a historical champion",
                context={"reason": "selection_failed", "fold_id": fold.fold_id, "detail": exc.context},
                cause=exc,
            ) from exc

        holdout_gate = HistoricalPromotionGate(
            registry=self.registry,
            suite=self.suite,
            window=fold.holdout_window,
            policy=PromotionPolicy(
                min_holdout_samples=1,
                min_coverage=0.0,
                min_promotion_margin=0.0,
                max_domain_regression=1.0,
                max_volatility=1.0,
                max_latest_drop=1.0,
            ),
        )
        try:
            selected_holdout = holdout_gate.evaluate(ranking.champion.model)
        except HistoricalEvaluationError as exc:
            raise HistoricalBacktestError(
                "selected champion has no evaluable forward holdout evidence",
                context={"reason": "selected_holdout_missing", "fold_id": fold.fold_id, "model": ranking.champion.model.key},
                cause=exc,
            ) from exc
        if selected_holdout.missing_required_domains or selected_holdout.coverage + _EPSILON < self.min_forward_coverage:
            raise HistoricalBacktestError(
                "selected champion lacks comparable forward suite coverage",
                context={
                    "reason": "selected_holdout_incomplete",
                    "fold_id": fold.fold_id,
                    "model": ranking.champion.model.key,
                    "coverage": selected_holdout.coverage,
                    "required_coverage": self.min_forward_coverage,
                    "missing_required_domains": [domain.value for domain in selected_holdout.missing_required_domains],
                },
            )

        eligible_models = scope if scope is not None else self.registry.models()
        oracle_candidates: list[HoldoutEvaluation] = []
        for model in eligible_models:
            try:
                evaluation = holdout_gate.evaluate(model)
            except HistoricalEvaluationError:
                continue
            if evaluation.missing_required_domains:
                continue
            if evaluation.coverage + _EPSILON < self.min_forward_coverage:
                continue
            oracle_candidates.append(evaluation)
        if not oracle_candidates:
            raise HistoricalBacktestError(
                "fold has no comparable forward candidates",
                context={
                    "reason": "no_forward_candidates",
                    "fold_id": fold.fold_id,
                    "required_coverage": self.min_forward_coverage,
                },
            )
        oracle_holdout = sorted(
            oracle_candidates,
            key=lambda item: (-item.score, -item.coverage, -item.samples, item.model.key),
        )[0]
        regret = max(0.0, oracle_holdout.score - selected_holdout.score)
        eligible_set = set(eligible_models)
        test_ids = sorted(
            snapshot.snapshot_id
            for snapshot in self.registry.snapshots()
            if fold.holdout_window.contains(snapshot.measured_at)
            and snapshot.benchmark.key in self.suite.benchmark_keys
            and snapshot.model in eligible_set
        )
        train_ids = sorted(snapshot.snapshot_id for snapshot in training)
        return BacktestFoldResult(
            fold=fold,
            ranking=ranking,
            selected_holdout=selected_holdout,
            oracle_model=oracle_holdout.model,
            oracle_holdout=oracle_holdout,
            regret=regret,
            candidate_count=len(oracle_candidates),
            train_snapshot_count=len(training),
            train_evidence_fingerprint=canonical_fingerprint(train_ids),
            test_evidence_fingerprint=canonical_fingerprint(test_ids),
        )


def summarize_backtest(report: BacktestReport) -> dict[str, object]:
    """JSON-friendly backtest surface for evidence logs and UI."""
    return {
        "plan": report.plan_key,
        "fold_count": report.fold_count,
        "min_forward_coverage": report.min_forward_coverage,
        "mean_selected_score": report.mean_selected_score,
        "mean_oracle_score": report.mean_oracle_score,
        "mean_regret": report.mean_regret,
        "worst_regret": report.worst_regret,
        "champion_stability": report.champion_stability,
        "unique_selected_models": [model.key for model in report.unique_selected_models],
        "plan_fingerprint": report.plan_fingerprint,
        "policy_fingerprint": report.policy_fingerprint,
        "suite_fingerprint": report.suite_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "folds": [
            {
                "fold_id": item.fold.fold_id,
                "train_end": item.fold.train_end,
                "test_start": item.fold.test_start,
                "test_end": item.fold.test_end,
                "selected_model": item.selected_model.key,
                "selected_score": item.selected_score,
                "oracle_model": item.oracle_model.key,
                "oracle_score": item.oracle_score,
                "regret": item.regret,
                "candidate_count": item.candidate_count,
                "train_snapshot_count": item.train_snapshot_count,
                "train_evidence_fingerprint": item.train_evidence_fingerprint,
                "test_evidence_fingerprint": item.test_evidence_fingerprint,
            }
            for item in report.folds
        ],
    }