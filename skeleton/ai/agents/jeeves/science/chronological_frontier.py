"""Chronological survivorship engine for scientific prediction techniques.

Jeeves should not jump directly from an old baseline to whatever is fashionable
in the current year.  This module makes historical progression executable:
techniques become eligible only after their historical availability, evidence is
usable only after its own knowledge/data cutoffs, challengers are compared on
identical forward targets, and a newer technique advances only when it earns a
complexity-adjusted, multi-metric improvement without violating mandatory
scientific gates.

The registry deliberately retains superseded techniques.  A method can lose the
frontier while remaining useful as a baseline, stress test, low-cost fallback,
or component of an ensemble.  "Old" and "wrong" are not synonyms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from ..agent.types import AgentContractError, finite_number, json_safe, positive_int, stable_fingerprint


class ForecastFamily(str, Enum):
    CHANCE = "chance"
    BAYESIAN = "bayesian"
    REGRESSION = "regression"
    STOCHASTIC_PROCESS = "stochastic_process"
    SMOOTHING = "smoothing"
    STATE_SPACE = "state_space"
    ARIMA = "arima"
    VOLATILITY = "volatility"
    HIDDEN_STATE = "hidden_state"
    MODEL_AVERAGING = "model_averaging"
    TREE_ENSEMBLE = "tree_ensemble"
    NEURAL = "neural"
    PROBABILISTIC = "probabilistic"
    CONFORMAL = "conformal"
    DEEP_FORECASTING = "deep_forecasting"
    FOUNDATION = "foundation"
    ROBUST_EVALUATION = "robust_evaluation"


class MetricDirection(str, Enum):
    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"


class FrontierDecisionStatus(str, Enum):
    PROMOTE = "promote"
    HOLD = "hold"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INCOMPARABLE = "incomparable"
    NOT_YET_AVAILABLE = "not_yet_available"


@dataclass(frozen=True, slots=True)
class ForecastTechnique:
    technique_id: str
    available_year: int
    name: str
    family: ForecastFamily
    scientific_role: str
    complexity_rank: int = 1
    assumptions: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    predecessors: tuple[str, ...] = ()
    survives_as: tuple[str, ...] = ("baseline",)
    sources: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        key = str(self.technique_id).strip().casefold()
        if not key:
            raise AgentContractError("technique_id is required")
        object.__setattr__(self, "technique_id", key)
        if isinstance(self.available_year, bool) or not isinstance(self.available_year, int):
            raise AgentContractError("available_year must be an integer")
        if not 1500 <= self.available_year <= 2100:
            raise AgentContractError("available_year outside supported historical range")
        if not str(self.name).strip() or not str(self.scientific_role).strip():
            raise AgentContractError("technique name and scientific_role are required")
        if not isinstance(self.family, ForecastFamily):
            object.__setattr__(self, "family", ForecastFamily(str(self.family)))
        object.__setattr__(self, "complexity_rank", positive_int("complexity_rank", self.complexity_rank, maximum=1000))
        object.__setattr__(self, "assumptions", tuple(str(x).strip() for x in self.assumptions if str(x).strip()))
        object.__setattr__(self, "failure_modes", tuple(str(x).strip() for x in self.failure_modes if str(x).strip()))
        object.__setattr__(self, "predecessors", tuple(str(x).strip().casefold() for x in self.predecessors if str(x).strip()))
        object.__setattr__(self, "survives_as", tuple(str(x).strip() for x in self.survives_as if str(x).strip()))
        object.__setattr__(self, "sources", tuple(str(x).strip() for x in self.sources if str(x).strip()))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.technique_id,
                "year": self.available_year,
                "name": self.name,
                "family": self.family.value,
                "role": self.scientific_role,
                "complexity": self.complexity_rank,
                "assumptions": self.assumptions,
                "failure_modes": self.failure_modes,
                "predecessors": self.predecessors,
                "survives_as": self.survives_as,
                "sources": self.sources,
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class MetricRule:
    name: str
    direction: MetricDirection
    weight: float
    introduced_year: int = 1500
    mandatory_from_year: int | None = None
    regression_tolerance: float = 0.02
    minimum_gain: float = 0.0

    def __post_init__(self) -> None:
        name = str(self.name).strip().casefold()
        if not name:
            raise AgentContractError("metric name is required")
        object.__setattr__(self, "name", name)
        if not isinstance(self.direction, MetricDirection):
            object.__setattr__(self, "direction", MetricDirection(str(self.direction)))
        weight = finite_number("metric weight", self.weight)
        if weight < 0:
            raise AgentContractError("metric weight must be non-negative")
        object.__setattr__(self, "weight", weight)
        if self.mandatory_from_year is not None and self.mandatory_from_year < self.introduced_year:
            raise AgentContractError("mandatory_from_year cannot precede introduced_year")
        tolerance = finite_number("regression_tolerance", self.regression_tolerance)
        gain = finite_number("minimum_gain", self.minimum_gain)
        if tolerance < 0 or gain < 0:
            raise AgentContractError("metric tolerance/gain must be non-negative")
        object.__setattr__(self, "regression_tolerance", tolerance)
        object.__setattr__(self, "minimum_gain", gain)

    def active(self, year: int) -> bool:
        return year >= self.introduced_year

    def mandatory(self, year: int) -> bool:
        return self.mandatory_from_year is not None and year >= self.mandatory_from_year


@dataclass(frozen=True, slots=True)
class HistoricalEvaluation:
    technique_id: str
    as_of_year: int
    knowledge_year: int
    data_cutoff_year: int
    benchmark_id: str
    target_window_fingerprint: str
    folds: int
    series_count: int
    domain_count: int
    independent_runs: int
    metrics: Mapping[str, float]
    leakage_audited: bool
    temporal_custody_verified: bool
    provenance_ids: tuple[str, ...]
    calibration_checked: bool = False
    compute_cost: float = 0.0
    energy_cost: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        key = str(self.technique_id).strip().casefold()
        if not key:
            raise AgentContractError("evaluation technique_id is required")
        object.__setattr__(self, "technique_id", key)
        for name in ("as_of_year", "knowledge_year", "data_cutoff_year"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise AgentContractError(f"{name} must be integer")
        if self.knowledge_year > self.as_of_year:
            raise AgentContractError("future knowledge cannot enter a historical evaluation")
        if self.data_cutoff_year > self.as_of_year:
            raise AgentContractError("future observations cannot enter a historical evaluation")
        if not str(self.benchmark_id).strip() or not str(self.target_window_fingerprint).strip():
            raise AgentContractError("benchmark and target-window identity are required")
        for name in ("folds", "series_count", "domain_count", "independent_runs"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000_000))
        metrics: dict[str, float] = {}
        for name, value in self.metrics.items():
            key_name = str(name).strip().casefold()
            if not key_name:
                raise AgentContractError("metric key cannot be empty")
            metrics[key_name] = finite_number(f"metric {key_name}", value)
        if not metrics:
            raise AgentContractError("evaluation requires metrics")
        object.__setattr__(self, "metrics", metrics)
        provenance = tuple(sorted({str(x) for x in self.provenance_ids if str(x)}))
        if not provenance:
            raise AgentContractError("evaluation requires provenance")
        object.__setattr__(self, "provenance_ids", provenance)
        for name in ("compute_cost", "energy_cost"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def custody_key(self) -> tuple[str, str, int]:
        return (str(self.benchmark_id), str(self.target_window_fingerprint), self.as_of_year)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "technique": self.technique_id,
                "as_of": self.as_of_year,
                "knowledge": self.knowledge_year,
                "data_cutoff": self.data_cutoff_year,
                "benchmark": self.benchmark_id,
                "window": self.target_window_fingerprint,
                "folds": self.folds,
                "series": self.series_count,
                "domains": self.domain_count,
                "runs": self.independent_runs,
                "metrics": dict(sorted(self.metrics.items())),
                "leakage": self.leakage_audited,
                "custody": self.temporal_custody_verified,
                "calibration": self.calibration_checked,
                "compute_cost": self.compute_cost,
                "energy_cost": self.energy_cost,
                "provenance": self.provenance_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class MetricComparison:
    metric: str
    incumbent_value: float
    challenger_value: float
    normalized_gain: float
    mandatory: bool
    regression: bool
    meaningful_improvement: bool


@dataclass(frozen=True, slots=True)
class ChallengerComparison:
    incumbent_id: str
    challenger_id: str
    year: int
    status: FrontierDecisionStatus
    weighted_gain: float
    complexity_penalty: float
    adjusted_gain: float
    metrics: tuple[MetricComparison, ...]
    failures: tuple[str, ...]
    reasons: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class YearFrontierDecision:
    year: int
    incumbent_before: str
    incumbent_after: str
    status: FrontierDecisionStatus
    considered: tuple[str, ...]
    comparisons: tuple[ChallengerComparison, ...]
    rationale: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ChronologicalReplayReport:
    initial_incumbent: str
    final_incumbent: str
    start_year: int
    end_year: int
    decisions: tuple[YearFrontierDecision, ...]
    survivor_ids: tuple[str, ...]
    fingerprint: str

    @property
    def promotion_years(self) -> tuple[int, ...]:
        return tuple(decision.year for decision in self.decisions if decision.status is FrontierDecisionStatus.PROMOTE)


@dataclass(frozen=True, slots=True)
class FrontierTournamentPolicy:
    minimum_folds: int = 12
    minimum_series: int = 20
    minimum_domains: int = 1
    minimum_independent_runs: int = 2
    minimum_adjusted_gain: float = 0.01
    complexity_penalty_per_rank: float = 0.002
    require_leakage_audit: bool = True
    require_temporal_custody: bool = True
    require_calibration_after_year: int = 1950

    def __post_init__(self) -> None:
        for name in ("minimum_folds", "minimum_series", "minimum_domains", "minimum_independent_runs"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000_000))
        for name in ("minimum_adjusted_gain", "complexity_penalty_per_rank"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)


class TechniqueRegistry:
    def __init__(self, techniques: Iterable[ForecastTechnique] = ()) -> None:
        self._items: dict[str, ForecastTechnique] = {}
        for technique in techniques:
            self.register(technique)

    def register(self, technique: ForecastTechnique) -> None:
        if not isinstance(technique, ForecastTechnique):
            raise TypeError("technique must be ForecastTechnique")
        if technique.technique_id in self._items:
            raise AgentContractError(f"duplicate technique: {technique.technique_id}")
        missing = [item for item in technique.predecessors if item not in self._items]
        if missing:
            raise AgentContractError(f"predecessors must be registered first: {missing}")
        for predecessor_id in technique.predecessors:
            if self._items[predecessor_id].available_year > technique.available_year:
                raise AgentContractError("technique predecessor comes from the future")
        self._items[technique.technique_id] = technique

    def get(self, technique_id: str) -> ForecastTechnique:
        key = str(technique_id).strip().casefold()
        try:
            return self._items[key]
        except KeyError as exc:
            raise AgentContractError(f"unknown technique: {key}") from exc

    def ordered(self) -> tuple[ForecastTechnique, ...]:
        return tuple(sorted(self._items.values(), key=lambda item: (item.available_year, item.technique_id)))

    def available(self, year: int) -> tuple[ForecastTechnique, ...]:
        return tuple(item for item in self.ordered() if item.available_year <= year)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint([(item.technique_id, item.fingerprint) for item in self.ordered()])


class ChronologicalFrontierTournament:
    """Replay scientific progress without hindsight or target-window drift."""

    def __init__(
        self,
        registry: TechniqueRegistry,
        *,
        metric_rules: Sequence[MetricRule] | None = None,
        policy: FrontierTournamentPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.metric_rules = tuple(metric_rules or default_metric_rules())
        if not self.metric_rules:
            raise AgentContractError("frontier tournament requires metric rules")
        if sum(rule.weight for rule in self.metric_rules) <= 0:
            raise AgentContractError("metric-rule weights sum to zero")
        self.policy = policy or FrontierTournamentPolicy()

    def _evidence_failures(self, technique: ForecastTechnique, evaluation: HistoricalEvaluation) -> list[str]:
        failures: list[str] = []
        if technique.available_year > evaluation.as_of_year:
            failures.append("technique_not_historically_available")
        if evaluation.folds < self.policy.minimum_folds:
            failures.append("insufficient_folds")
        if evaluation.series_count < self.policy.minimum_series:
            failures.append("insufficient_series")
        if evaluation.domain_count < self.policy.minimum_domains:
            failures.append("insufficient_domains")
        if evaluation.independent_runs < self.policy.minimum_independent_runs:
            failures.append("insufficient_independent_runs")
        if self.policy.require_leakage_audit and not evaluation.leakage_audited:
            failures.append("missing_leakage_audit")
        if self.policy.require_temporal_custody and not evaluation.temporal_custody_verified:
            failures.append("missing_temporal_custody")
        if evaluation.as_of_year >= self.policy.require_calibration_after_year and not evaluation.calibration_checked:
            failures.append("missing_calibration_check")
        return failures

    @staticmethod
    def _normalized_gain(rule: MetricRule, incumbent: float, challenger: float) -> float:
        scale = max(abs(incumbent), abs(challenger), 1e-12)
        if rule.direction is MetricDirection.LOWER_IS_BETTER:
            return (incumbent - challenger) / scale
        return (challenger - incumbent) / scale

    def compare(
        self,
        incumbent_eval: HistoricalEvaluation,
        challenger_eval: HistoricalEvaluation,
    ) -> ChallengerComparison:
        incumbent = self.registry.get(incumbent_eval.technique_id)
        challenger = self.registry.get(challenger_eval.technique_id)
        year = challenger_eval.as_of_year
        failures = self._evidence_failures(incumbent, incumbent_eval)
        failures.extend(self._evidence_failures(challenger, challenger_eval))
        reasons: list[str] = []
        if incumbent_eval.as_of_year != challenger_eval.as_of_year:
            failures.append("different_simulated_year")
        if incumbent_eval.custody_key != challenger_eval.custody_key:
            failures.append("different_target_custody")
        if challenger.technique_id == incumbent.technique_id:
            failures.append("self_comparison")

        metric_comparisons: list[MetricComparison] = []
        weighted_numerator = 0.0
        weight_total = 0.0
        for rule in self.metric_rules:
            if not rule.active(year):
                continue
            left = incumbent_eval.metrics.get(rule.name)
            right = challenger_eval.metrics.get(rule.name)
            if left is None or right is None:
                if rule.mandatory(year):
                    failures.append(f"missing_mandatory_metric:{rule.name}")
                continue
            gain = self._normalized_gain(rule, left, right)
            regression = gain < -rule.regression_tolerance
            improved = gain >= rule.minimum_gain and gain > 0
            if rule.mandatory(year) and regression:
                failures.append(f"mandatory_metric_regression:{rule.name}")
            metric_comparisons.append(
                MetricComparison(
                    metric=rule.name,
                    incumbent_value=left,
                    challenger_value=right,
                    normalized_gain=gain,
                    mandatory=rule.mandatory(year),
                    regression=regression,
                    meaningful_improvement=improved,
                )
            )
            weighted_numerator += rule.weight * gain
            weight_total += rule.weight

        if weight_total <= 0:
            failures.append("no_comparable_metrics")
            weighted_gain = 0.0
        else:
            weighted_gain = weighted_numerator / weight_total

        complexity_delta = max(0, challenger.complexity_rank - incumbent.complexity_rank)
        complexity_penalty = self.policy.complexity_penalty_per_rank * complexity_delta
        adjusted_gain = weighted_gain - complexity_penalty

        if failures:
            incomparable_markers = {"different_simulated_year", "different_target_custody", "self_comparison", "no_comparable_metrics"}
            if any(item in incomparable_markers for item in failures):
                status = FrontierDecisionStatus.INCOMPARABLE
            elif "technique_not_historically_available" in failures:
                status = FrontierDecisionStatus.NOT_YET_AVAILABLE
            else:
                status = FrontierDecisionStatus.INSUFFICIENT_EVIDENCE
            reasons.append("challenger cannot be promoted because comparison contract failed")
        elif adjusted_gain >= self.policy.minimum_adjusted_gain and any(item.meaningful_improvement for item in metric_comparisons):
            status = FrontierDecisionStatus.PROMOTE
            reasons.append("challenger earned complexity-adjusted forward improvement")
        else:
            status = FrontierDecisionStatus.HOLD
            reasons.append("incumbent survives; challenger did not clear the promotion margin")

        payload = {
            "incumbent": incumbent.technique_id,
            "challenger": challenger.technique_id,
            "year": year,
            "status": status.value,
            "weighted_gain": weighted_gain,
            "complexity_penalty": complexity_penalty,
            "adjusted_gain": adjusted_gain,
            "metrics": [
                {
                    "metric": item.metric,
                    "incumbent": item.incumbent_value,
                    "challenger": item.challenger_value,
                    "gain": item.normalized_gain,
                    "mandatory": item.mandatory,
                    "regression": item.regression,
                    "improvement": item.meaningful_improvement,
                }
                for item in metric_comparisons
            ],
            "failures": sorted(set(failures)),
            "reasons": reasons,
        }
        return ChallengerComparison(
            incumbent_id=incumbent.technique_id,
            challenger_id=challenger.technique_id,
            year=year,
            status=status,
            weighted_gain=weighted_gain,
            complexity_penalty=complexity_penalty,
            adjusted_gain=adjusted_gain,
            metrics=tuple(metric_comparisons),
            failures=tuple(sorted(set(failures))),
            reasons=tuple(reasons),
            fingerprint=stable_fingerprint(payload),
        )

    def replay(
        self,
        initial_incumbent: str,
        evaluations: Sequence[HistoricalEvaluation],
        *,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> ChronologicalReplayReport:
        initial = self.registry.get(initial_incumbent)
        if not evaluations:
            raise AgentContractError("chronological replay requires evaluations")
        eval_map: dict[tuple[int, str], HistoricalEvaluation] = {}
        years: set[int] = set()
        for evaluation in evaluations:
            self.registry.get(evaluation.technique_id)
            key = (evaluation.as_of_year, evaluation.technique_id)
            existing = eval_map.get(key)
            if existing is not None and existing.fingerprint != evaluation.fingerprint:
                raise AgentContractError(f"conflicting evaluation for {key}")
            eval_map[key] = evaluation
            years.add(evaluation.as_of_year)
        lower = min(years) if start_year is None else start_year
        upper = max(years) if end_year is None else end_year
        if lower > upper:
            raise AgentContractError("start_year exceeds end_year")
        if lower < initial.available_year:
            raise AgentContractError("initial incumbent is not available at replay start")

        incumbent_id = initial.technique_id
        survivor_ids: set[str] = {incumbent_id}
        decisions: list[YearFrontierDecision] = []
        for year in range(lower, upper + 1):
            incumbent_eval = eval_map.get((year, incumbent_id))
            challengers = [
                technique
                for technique in self.registry.available(year)
                if technique.technique_id != incumbent_id and (year, technique.technique_id) in eval_map
            ]
            comparisons: list[ChallengerComparison] = []
            rationale: list[str] = []
            status = FrontierDecisionStatus.HOLD
            before = incumbent_id
            if incumbent_eval is None:
                status = FrontierDecisionStatus.INSUFFICIENT_EVIDENCE
                rationale.append("incumbent has no same-year evidence; frontier is frozen")
            else:
                for challenger in challengers:
                    comparisons.append(self.compare(incumbent_eval, eval_map[(year, challenger.technique_id)]))
                promotable = [item for item in comparisons if item.status is FrontierDecisionStatus.PROMOTE]
                if promotable:
                    winner = max(promotable, key=lambda item: (item.adjusted_gain, -self.registry.get(item.challenger_id).complexity_rank, item.challenger_id))
                    incumbent_id = winner.challenger_id
                    survivor_ids.add(incumbent_id)
                    status = FrontierDecisionStatus.PROMOTE
                    rationale.append(f"{winner.challenger_id} won the same-year challenger arena")
                elif comparisons:
                    rationale.append("all challengers were held, incomparable, or insufficiently evidenced")
                else:
                    rationale.append("no historically available challenger has same-year evidence")
            payload = {
                "year": year,
                "before": before,
                "after": incumbent_id,
                "status": status.value,
                "considered": [item.technique_id for item in challengers],
                "comparisons": [item.fingerprint for item in comparisons],
                "rationale": rationale,
            }
            decisions.append(
                YearFrontierDecision(
                    year=year,
                    incumbent_before=before,
                    incumbent_after=incumbent_id,
                    status=status,
                    considered=tuple(item.technique_id for item in challengers),
                    comparisons=tuple(comparisons),
                    rationale=tuple(rationale),
                    fingerprint=stable_fingerprint(payload),
                )
            )

        report_payload = {
            "registry": self.registry.fingerprint,
            "initial": initial.technique_id,
            "final": incumbent_id,
            "start": lower,
            "end": upper,
            "decisions": [item.fingerprint for item in decisions],
            "survivors": sorted(survivor_ids),
        }
        return ChronologicalReplayReport(
            initial_incumbent=initial.technique_id,
            final_incumbent=incumbent_id,
            start_year=lower,
            end_year=upper,
            decisions=tuple(decisions),
            survivor_ids=tuple(sorted(survivor_ids)),
            fingerprint=stable_fingerprint(report_payload),
        )


def default_metric_rules() -> tuple[MetricRule, ...]:
    """Progressively stronger evidence standards, applied only after their era."""

    return (
        MetricRule("mae", MetricDirection.LOWER_IS_BETTER, 0.18, introduced_year=1805, mandatory_from_year=1805, regression_tolerance=0.03),
        MetricRule("rmse", MetricDirection.LOWER_IS_BETTER, 0.12, introduced_year=1805, mandatory_from_year=1805, regression_tolerance=0.04),
        MetricRule("brier", MetricDirection.LOWER_IS_BETTER, 0.15, introduced_year=1950, mandatory_from_year=1950, regression_tolerance=0.03),
        MetricRule("log_loss", MetricDirection.LOWER_IS_BETTER, 0.20, introduced_year=1952, mandatory_from_year=1952, regression_tolerance=0.03),
        MetricRule("coverage_gap", MetricDirection.LOWER_IS_BETTER, 0.10, introduced_year=1960, mandatory_from_year=1970, regression_tolerance=0.04),
        MetricRule("crps", MetricDirection.LOWER_IS_BETTER, 0.15, introduced_year=1970, mandatory_from_year=2000, regression_tolerance=0.03),
        MetricRule("calibration_ece", MetricDirection.LOWER_IS_BETTER, 0.07, introduced_year=2000, mandatory_from_year=2017, regression_tolerance=0.03),
        MetricRule("energy_efficiency", MetricDirection.HIGHER_IS_BETTER, 0.03, introduced_year=2024, mandatory_from_year=None, regression_tolerance=0.20),
    )


def default_prediction_lineage() -> TechniqueRegistry:
    """Curated milestones; inclusion means historical relevance, not superiority."""

    records = (
        ForecastTechnique(
            "huygens_expectation_1657", 1657, "Expectation for games of chance", ForecastFamily.CHANCE,
            "Exact finite chance and expectation remain a sanity baseline for probabilistic reasoning.",
            complexity_rank=1,
            survives_as=("exact finite baseline", "game probability test oracle"),
            sources=("Huygens, De ratiociniis in ludo aleae, 1657",),
        ),
        ForecastTechnique(
            "bayes_inverse_1763", 1763, "Bayesian inverse probability", ForecastFamily.BAYESIAN,
            "Update uncertainty about latent hypotheses from observations.",
            complexity_rank=2, predecessors=("huygens_expectation_1657",),
            survives_as=("posterior inference", "parameter uncertainty", "model weighting"),
            sources=("Bayes, posthumous essay, 1763",),
        ),
        ForecastTechnique(
            "legendre_least_squares_1805", 1805, "Least squares", ForecastFamily.REGRESSION,
            "Fit predictive relations by minimizing squared residuals; preserve as transparent regression baseline.",
            complexity_rank=2, predecessors=("huygens_expectation_1657",),
            survives_as=("linear baseline", "calibration diagnostic", "trend component"),
            sources=("Legendre, Nouvelles méthodes..., 1805", "Gauss, Theoria Motus, 1809"),
        ),
        ForecastTechnique(
            "markov_chain_1906", 1906, "Markov chain", ForecastFamily.STOCHASTIC_PROCESS,
            "Represent state transitions when the modeled state makes the future conditionally history-independent.",
            complexity_rank=3, predecessors=("bayes_inverse_1763",),
            assumptions=("state is sufficiently Markov for the task",),
            survives_as=("transition model", "regime dynamics", "control primitive"),
            sources=("Markov, early chain work, 1906",),
        ),
        ForecastTechnique(
            "yule_ar_1927", 1927, "Stochastic autoregression", ForecastFamily.STOCHASTIC_PROCESS,
            "Model serial dependence as a stochastic process instead of deterministic periodicity alone.",
            complexity_rank=3, predecessors=("legendre_least_squares_1805", "markov_chain_1906"),
            survives_as=("AR baseline", "residual diagnostic", "linear dynamics component"),
            sources=("Yule, 1927 stochastic time-series work",),
        ),
        ForecastTechnique(
            "wiener_filter_1949", 1949, "Wiener prediction/filtering", ForecastFamily.STATE_SPACE,
            "Optimal linear filtering/prediction under second-order stochastic assumptions.",
            complexity_rank=4, predecessors=("yule_ar_1927",),
            survives_as=("linear filter baseline", "signal/noise decomposition"),
            sources=("Wiener, Extrapolation, Interpolation, and Smoothing of Stationary Time Series, 1949",),
        ),
        ForecastTechnique(
            "holt_smoothing_1957", 1957, "Holt exponential smoothing", ForecastFamily.SMOOTHING,
            "Cheap adaptive level/trend forecasting with exponentially decayed history.",
            complexity_rank=2, predecessors=("legendre_least_squares_1805",),
            survives_as=("fast baseline", "level/trend component", "low-data fallback"),
            sources=("Holt, 1957",),
        ),
        ForecastTechnique(
            "kalman_1960", 1960, "Kalman filtering", ForecastFamily.STATE_SPACE,
            "Recursive latent-state estimation with explicit predictive covariance in the linear-Gaussian case.",
            complexity_rank=4, predecessors=("wiener_filter_1949",),
            survives_as=("state estimator", "uncertainty baseline", "structural time-series core"),
            sources=("Kalman, 1960",),
        ),
        ForecastTechnique(
            "winters_1960", 1960, "Holt-Winters seasonal smoothing", ForecastFamily.SMOOTHING,
            "Extend exponential smoothing with seasonal structure.",
            complexity_rank=3, predecessors=("holt_smoothing_1957",),
            survives_as=("seasonal baseline", "interpretable production forecaster"),
            sources=("Winters, Management Science, 1960",),
        ),
        ForecastTechnique(
            "baum_hmm_1966", 1966, "Hidden Markov model inference", ForecastFamily.HIDDEN_STATE,
            "Infer latent discrete regimes that probabilistically emit observations.",
            complexity_rank=5, predecessors=("markov_chain_1906", "bayes_inverse_1763"),
            survives_as=("regime challenger", "latent-state diagnostic"),
            sources=("Baum and Petrie, 1966; Baum-Welch era",),
        ),
        ForecastTechnique(
            "box_jenkins_1970", 1970, "Box-Jenkins ARIMA", ForecastFamily.ARIMA,
            "Systematic identification, estimation and residual checking for autoregressive/integrated/moving-average models.",
            complexity_rank=4, predecessors=("yule_ar_1927",),
            survives_as=("strong statistical baseline", "residual model", "seasonal ARIMA component"),
            sources=("Box and Jenkins, Time Series Analysis, 1970",),
        ),
        ForecastTechnique(
            "aic_1974", 1974, "Akaike information criterion", ForecastFamily.ROBUST_EVALUATION,
            "Penalize fit by model complexity instead of selecting by in-sample fit alone.",
            complexity_rank=2, predecessors=("legendre_least_squares_1805",),
            survives_as=("complexity diagnostic", "candidate-screening baseline"),
            sources=("Akaike, 1974",),
        ),
        ForecastTechnique(
            "arch_1982", 1982, "ARCH conditional variance", ForecastFamily.VOLATILITY,
            "Model time-varying conditional uncertainty instead of assuming constant residual variance.",
            complexity_rank=5, predecessors=("box_jenkins_1970",),
            survives_as=("heteroskedasticity diagnostic", "conditional-risk model"),
            sources=("Engle, 1982",),
        ),
        ForecastTechnique(
            "prequential_1984", 1984, "Prequential evaluation", ForecastFamily.ROBUST_EVALUATION,
            "Judge sequential predictive distributions by forecasts made before outcomes are observed.",
            complexity_rank=2, predecessors=("aic_1974",),
            survives_as=("temporal custody rule", "online scoring protocol"),
            sources=("Dawid, JRSS A, 1984",),
        ),
        ForecastTechnique(
            "garch_1986", 1986, "GARCH conditional variance", ForecastFamily.VOLATILITY,
            "Generalize ARCH with persistent conditional variance dynamics.",
            complexity_rank=6, predecessors=("arch_1982",),
            survives_as=("volatility baseline", "tail/risk challenger"),
            sources=("Bollerslev, 1986",),
        ),
        ForecastTechnique(
            "lstm_1997", 1997, "Long short-term memory", ForecastFamily.NEURAL,
            "Learn nonlinear recurrent representations with gated long-range memory.",
            complexity_rank=8, predecessors=("yule_ar_1927",),
            survives_as=("sequence-model challenger",),
            sources=("Hochreiter and Schmidhuber, 1997",),
        ),
        ForecastTechnique(
            "bma_1999", 1999, "Bayesian model averaging", ForecastFamily.MODEL_AVERAGING,
            "Carry model uncertainty into prediction instead of conditioning on one selected model.",
            complexity_rank=6, predecessors=("bayes_inverse_1763", "aic_1974"),
            survives_as=("model uncertainty", "ensemble posterior"),
            sources=("Hoeting et al., Statistical Science, 1999",),
        ),
        ForecastTechnique(
            "gradient_boosting_2001", 2001, "Gradient boosting machines", ForecastFamily.TREE_ENSEMBLE,
            "Build nonlinear predictive ensembles by stage-wise loss reduction.",
            complexity_rank=7, predecessors=("legendre_least_squares_1805",),
            survives_as=("tabular/covariate challenger", "nonlinear ensemble"),
            sources=("Friedman, 2001",),
        ),
        ForecastTechnique(
            "conformal_2005", 2005, "Conformal prediction", ForecastFamily.CONFORMAL,
            "Wrap predictive systems with finite-sample marginal coverage under exchangeability.",
            complexity_rank=5, predecessors=("prequential_1984",),
            assumptions=("exchangeability for classical finite-sample coverage",),
            survives_as=("coverage wrapper", "calibration stress test"),
            sources=("Vovk, Gammerman and Shafer, Algorithmic Learning in a Random World, 2005",),
        ),
        ForecastTechnique(
            "gpml_2006", 2006, "Gaussian-process regression", ForecastFamily.PROBABILISTIC,
            "Nonparametric Bayesian function inference with explicit predictive uncertainty.",
            complexity_rank=7, predecessors=("bayes_inverse_1763", "legendre_least_squares_1805"),
            survives_as=("small-data nonlinear probabilistic model", "kernel diagnostic"),
            sources=("Rasmussen and Williams, Gaussian Processes for Machine Learning, 2006",),
        ),
        ForecastTechnique(
            "deepar_2017", 2017, "DeepAR", ForecastFamily.DEEP_FORECASTING,
            "Global autoregressive recurrent probabilistic forecasting across related series.",
            complexity_rank=9, predecessors=("lstm_1997", "bma_1999"),
            survives_as=("global probabilistic neural challenger",),
            sources=("Salinas et al., DeepAR, 2017",),
        ),
        ForecastTechnique(
            "nbeats_2019", 2019, "N-BEATS", ForecastFamily.DEEP_FORECASTING,
            "Deep residual basis expansion for univariate forecasting.",
            complexity_rank=9, predecessors=("lstm_1997",),
            survives_as=("deep point-forecast challenger",),
            sources=("Oreshkin et al., N-BEATS, 2019",),
        ),
        ForecastTechnique(
            "m4_hybrid_2020", 2020, "M4 hybrid and combination evidence", ForecastFamily.MODEL_AVERAGING,
            "Treat heterogeneous combinations as first-class challengers because empirical competitions show complementarity.",
            complexity_rank=8, predecessors=("bma_1999", "gradient_boosting_2001", "box_jenkins_1970"),
            survives_as=("cross-family ensemble", "benchmark lesson"),
            sources=("Makridakis et al., International Journal of Forecasting, 2020",),
        ),
        ForecastTechnique(
            "m5_ml_2022", 2022, "M5 global ML forecasting evidence", ForecastFamily.TREE_ENSEMBLE,
            "Use global covariate-aware ML as a serious challenger while preserving statistical baselines and combinations.",
            complexity_rank=8, predecessors=("gradient_boosting_2001", "m4_hybrid_2020"),
            survives_as=("global tabular forecaster", "covariate-rich challenger"),
            sources=("Makridakis et al., M5 accuracy competition results, 2022",),
        ),
        ForecastTechnique(
            "timesfm_2024", 2024, "TimesFM foundation forecasting", ForecastFamily.FOUNDATION,
            "Pretrained decoder-only time-series model for zero-shot transfer; must be evaluated on uncontaminated future data.",
            complexity_rank=12, predecessors=("deepar_2017", "m5_ml_2022"),
            survives_as=("zero-shot challenger",),
            sources=("Das et al., ICML 2024 / TimesFM",),
        ),
        ForecastTechnique(
            "moirai_2024", 2024, "Moirai universal forecasting transformer", ForecastFamily.FOUNDATION,
            "Cross-frequency pretrained universal forecaster with multivariate support.",
            complexity_rank=12, predecessors=("deepar_2017", "m5_ml_2022"),
            survives_as=("zero-shot universal challenger",),
            sources=("Woo et al., ICML 2024",),
        ),
        ForecastTechnique(
            "chronos_2024", 2024, "Chronos tokenized time-series foundation model", ForecastFamily.FOUNDATION,
            "Generate probabilistic trajectories from tokenized time series; benchmark contamination remains an explicit threat.",
            complexity_rank=12, predecessors=("deepar_2017",),
            survives_as=("zero-shot probabilistic challenger",),
            sources=("Ansari et al., TMLR 2024",),
        ),
        ForecastTechnique(
            "tsfm_integrity_2025", 2025, "Foundation-model benchmark integrity", ForecastFamily.ROBUST_EVALUATION,
            "Require uncontaminated truly future/out-of-sample evaluation before zero-shot performance can earn promotion.",
            complexity_rank=3, predecessors=("prequential_1984", "timesfm_2024", "moirai_2024", "chronos_2024"),
            survives_as=("benchmark contamination gate", "future-data custody rule"),
            sources=("Time Series Foundation Models: Benchmarking Challenges and Requirements, 2025",),
        ),
        ForecastTechnique(
            "accuracy_energy_2026", 2026, "Accuracy-energy frontier evaluation", ForecastFamily.ROBUST_EVALUATION,
            "Treat energy/latency as measured decision costs alongside accuracy for large forecasting models.",
            complexity_rank=3, predecessors=("tsfm_integrity_2025",),
            survives_as=("deployment-efficiency gate", "model-family arbitration criterion"),
            sources=("Guibert et al., PMLR 2026 accuracy/energy TSFM benchmark",),
        ),
        ForecastTechnique(
            "semantic_adapter_2026", 2026, "Semantic interpretive probability adapter", ForecastFamily.PROBABILISTIC,
            "Bridge pre-existing semantic forecasts into the predictive exchange without treating interpretation as evidence or historical method identity.",
            complexity_rank=2, predecessors=("prequential_1984",),
            assumptions=("semantic probability was created before the request cutoff", "supporting evidence is already in request custody"),
            failure_modes=("interpretive probability is not empirical evidence", "target or forecast identity drift invalidates the binding"),
            survives_as=("interpretive forecast adapter", "prequential semantic calibration bridge"),
            sources=("Skeleton semantic prediction and predictive exchange contract, 2026",),
        ),
    )
    return TechniqueRegistry(records)
