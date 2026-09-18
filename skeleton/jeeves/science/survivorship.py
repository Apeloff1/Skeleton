"""Cross-domain historical survivorship for Jeeves scientific architecture.

This is the generalization of the forecasting-only chronological tournament.
It can govern memory, retrieval, probability, semantics, prediction, causality,
control, planning, compilers, decompilers and verification with the same rule:

    a newer method is eligible only when it existed,
    is judged only with information then available,
    is compared on the same forward target,
    must preserve mandatory invariants,
    and replaces an incumbent only after measured improvement.

Losing the active frontier does not erase an old method. Survivors can remain
as baselines, fallbacks, ensemble members, diagnostics or stress tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from ..agent.types import AgentContractError, finite_number, json_safe, positive_int, stable_fingerprint
from .lineage import EvidenceGrade


class ScientificFacet(str, Enum):
    MEMORY = "memory"
    CONTEXT_RETRIEVAL = "context_retrieval"
    PROBABILITY = "probability"
    UNCERTAINTY = "uncertainty"
    SEMANTICS = "semantics"
    PREDICTIVE_MODELING = "predictive_modeling"
    CAUSALITY = "causality"
    CONTROL = "control"
    PLANNING = "planning"
    METAREASONING = "metareasoning"
    COMPILER = "compiler"
    DECOMPILER = "decompiler"
    PROGRAM_ANALYSIS = "program_analysis"
    VERIFICATION = "verification"
    GAME_REASONING = "game_reasoning"


class MetricOrientation(str, Enum):
    HIGHER = "higher"
    LOWER = "lower"


class SurvivorRole(str, Enum):
    ACTIVE = "active"
    BASELINE = "baseline"
    ENSEMBLE = "ensemble"
    FALLBACK = "fallback"
    STRESS_TEST = "stress_test"
    SHADOW = "shadow"
    REJECTED = "rejected"


class HistoricalDecision(str, Enum):
    PROMOTE = "promote"
    HOLD = "hold"
    SHADOW = "shadow"
    INCOMPARABLE = "incomparable"
    NOT_AVAILABLE = "not_available"
    LEAKAGE_REJECTED = "leakage_rejected"
    INVARIANT_REJECTED = "invariant_rejected"


@dataclass(frozen=True, slots=True)
class HistoricalMethod:
    method_id: str
    available_year: int
    name: str
    facet: ScientificFacet
    retained_principle: str
    evidence_grade: EvidenceGrade
    complexity_rank: int = 1
    predecessors: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    survives_as: tuple[SurvivorRole, ...] = (
        SurvivorRole.BASELINE,
        SurvivorRole.STRESS_TEST,
    )
    sources: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        key = str(self.method_id).strip().casefold()
        if not key:
            raise AgentContractError("method_id is required")
        object.__setattr__(self, "method_id", key)
        if isinstance(self.available_year, bool) or not isinstance(self.available_year, int):
            raise AgentContractError("available_year must be integer")
        if not 1500 <= self.available_year <= 2100:
            raise AgentContractError("available_year outside supported range")
        if not str(self.name).strip() or not str(self.retained_principle).strip():
            raise AgentContractError("name and retained_principle are required")
        if not isinstance(self.facet, ScientificFacet):
            object.__setattr__(self, "facet", ScientificFacet(str(self.facet)))
        if not isinstance(self.evidence_grade, EvidenceGrade):
            object.__setattr__(self, "evidence_grade", EvidenceGrade(str(self.evidence_grade)))
        object.__setattr__(
            self,
            "complexity_rank",
            positive_int("complexity_rank", self.complexity_rank, maximum=10_000),
        )
        object.__setattr__(
            self,
            "predecessors",
            tuple(str(item).strip().casefold() for item in self.predecessors if str(item).strip()),
        )
        for name in ("assumptions", "invariants", "failure_modes", "sources"):
            object.__setattr__(
                self,
                name,
                tuple(str(item).strip() for item in getattr(self, name) if str(item).strip()),
            )
        roles = tuple(
            role if isinstance(role, SurvivorRole) else SurvivorRole(str(role))
            for role in self.survives_as
        )
        object.__setattr__(self, "survives_as", roles)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.method_id,
                "year": self.available_year,
                "name": self.name,
                "facet": self.facet.value,
                "principle": self.retained_principle,
                "grade": self.evidence_grade.value,
                "complexity": self.complexity_rank,
                "predecessors": self.predecessors,
                "assumptions": self.assumptions,
                "invariants": self.invariants,
                "failure_modes": self.failure_modes,
                "survives_as": [role.value for role in self.survives_as],
                "sources": self.sources,
            }
        )


@dataclass(frozen=True, slots=True)
class HistoricalEvaluation:
    method_id: str
    benchmark_id: str
    as_of_year: int
    knowledge_cutoff_year: int
    target_start_year: int
    target_end_year: int
    metrics: Mapping[str, float]
    sample_count: int
    independent_replications: int = 1
    adversarial_runs: int = 0
    verified: bool = False
    invariant_failures: tuple[str, ...] = ()
    dataset_fingerprint: str = ""
    code_fingerprint: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "method_id", str(self.method_id).strip().casefold())
        if not self.method_id or not str(self.benchmark_id).strip():
            raise AgentContractError("evaluation requires method_id and benchmark_id")
        if self.knowledge_cutoff_year > self.target_start_year:
            raise AgentContractError("knowledge cutoff crosses target start")
        if self.target_start_year > self.target_end_year:
            raise AgentContractError("target window is reversed")
        if self.target_end_year > self.as_of_year:
            raise AgentContractError("as_of_year precedes observed target end")
        for name in ("sample_count", "independent_replications", "adversarial_runs"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")
        normalized = {}
        for key, value in self.metrics.items():
            if not str(key).strip():
                raise AgentContractError("metric name cannot be blank")
            normalized[str(key).strip().casefold()] = finite_number(str(key), value)
        object.__setattr__(self, "metrics", normalized)
        object.__setattr__(
            self,
            "invariant_failures",
            tuple(sorted({str(item) for item in self.invariant_failures if str(item)})),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def custody_fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "method": self.method_id,
                "benchmark": self.benchmark_id,
                "as_of": self.as_of_year,
                "cutoff": self.knowledge_cutoff_year,
                "target": (self.target_start_year, self.target_end_year),
                "metrics": dict(sorted(self.metrics.items())),
                "n": self.sample_count,
                "replications": self.independent_replications,
                "adversarial": self.adversarial_runs,
                "verified": self.verified,
                "failures": self.invariant_failures,
                "dataset": self.dataset_fingerprint,
                "code": self.code_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class MetricStandard:
    name: str
    orientation: MetricOrientation
    weight: float = 1.0
    introduced_year: int = 1500
    mandatory_from_year: int | None = None
    minimum_candidate: float | None = None
    maximum_regression: float = 0.0
    minimum_improvement: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name).strip().casefold())
        if not self.name:
            raise AgentContractError("metric standard requires name")
        if not isinstance(self.orientation, MetricOrientation):
            object.__setattr__(self, "orientation", MetricOrientation(str(self.orientation)))
        weight = finite_number("weight", self.weight)
        if weight < 0:
            raise AgentContractError("metric weight must be non-negative")
        object.__setattr__(self, "weight", weight)
        if self.mandatory_from_year is not None and self.mandatory_from_year < self.introduced_year:
            raise AgentContractError("mandatory year cannot precede introduction")
        for name in ("maximum_regression", "minimum_improvement"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)

    def orient(self, value: float) -> float:
        return value if self.orientation is MetricOrientation.HIGHER else -value


@dataclass(frozen=True, slots=True)
class SurvivorshipPolicy:
    minimum_samples: int = 20
    minimum_replications: int = 2
    minimum_adversarial_runs: int = 0
    require_verification_from_year: int | None = None
    complexity_penalty: float = 0.0025
    minimum_weighted_gain: float = 0.0

    def __post_init__(self) -> None:
        for name in ("minimum_samples", "minimum_replications", "minimum_adversarial_runs"):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=100_000_000)
                if getattr(self, name) > 0
                else 0,
            )
        penalty = finite_number("complexity_penalty", self.complexity_penalty)
        if penalty < 0:
            raise AgentContractError("complexity_penalty must be non-negative")
        object.__setattr__(self, "complexity_penalty", penalty)
        object.__setattr__(
            self,
            "minimum_weighted_gain",
            finite_number("minimum_weighted_gain", self.minimum_weighted_gain),
        )


@dataclass(frozen=True, slots=True)
class MethodComparison:
    incumbent_id: str
    challenger_id: str
    benchmark_id: str | None
    weighted_gain: float
    complexity_adjusted_gain: float
    metric_deltas: Mapping[str, float]
    mandatory_failures: tuple[str, ...]
    evidence_failures: tuple[str, ...]
    invariant_failures: tuple[str, ...]
    decision: HistoricalDecision
    rationale: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class YearFacetFrontier:
    year: int
    facet: ScientificFacet
    active_method_id: str | None
    eligible_method_ids: tuple[str, ...]
    survivor_roles: Mapping[str, tuple[SurvivorRole, ...]]
    comparisons: tuple[MethodComparison, ...]
    fingerprint: str


class HistoricalSurvivorshipEngine:
    """Chronological, no-hindsight tournament across one scientific facet."""

    def __init__(
        self,
        methods: Iterable[HistoricalMethod] = (),
        evaluations: Iterable[HistoricalEvaluation] = (),
        *,
        policy: SurvivorshipPolicy | None = None,
    ) -> None:
        self.policy = policy or SurvivorshipPolicy()
        self._methods: dict[str, HistoricalMethod] = {}
        self._evaluations: list[HistoricalEvaluation] = []
        for method in methods:
            self.register_method(method)
        for evaluation in evaluations:
            self.register_evaluation(evaluation)

    def register_method(self, method: HistoricalMethod) -> None:
        if not isinstance(method, HistoricalMethod):
            raise TypeError("method must be HistoricalMethod")
        unknown = [item for item in method.predecessors if item not in self._methods]
        if unknown:
            raise AgentContractError(
                "method references unregistered predecessors: " + ", ".join(unknown)
            )
        existing = self._methods.get(method.method_id)
        if existing is not None and existing != method:
            raise AgentContractError("method id already registered with different content")
        self._methods[method.method_id] = method

    def register_evaluation(self, evaluation: HistoricalEvaluation) -> None:
        if evaluation.method_id not in self._methods:
            raise AgentContractError("evaluation references unknown method")
        method = self._methods[evaluation.method_id]
        if method.available_year > evaluation.knowledge_cutoff_year:
            raise AgentContractError("evaluation uses method before historical availability")
        self._evaluations.append(evaluation)

    def methods(
        self,
        facet: ScientificFacet,
        *,
        through_year: int,
    ) -> tuple[HistoricalMethod, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._methods.values()
                    if item.facet is facet and item.available_year <= through_year
                ),
                key=lambda item: (item.available_year, item.method_id),
            )
        )

    def _valid_evaluations(
        self,
        method_id: str,
        *,
        as_of_year: int,
    ) -> tuple[HistoricalEvaluation, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._evaluations
                    if item.method_id == method_id
                    and item.as_of_year <= as_of_year
                    and item.target_end_year <= as_of_year
                    and item.knowledge_cutoff_year <= item.target_start_year
                ),
                key=lambda item: (
                    item.as_of_year,
                    item.target_end_year,
                    item.benchmark_id,
                    item.custody_fingerprint,
                ),
            )
        )

    def _comparable_pair(
        self,
        incumbent_id: str,
        challenger_id: str,
        *,
        year: int,
    ) -> tuple[HistoricalEvaluation, HistoricalEvaluation] | None:
        incumbent = self._valid_evaluations(incumbent_id, as_of_year=year)
        challenger = self._valid_evaluations(challenger_id, as_of_year=year)
        pairs = []
        for left in incumbent:
            for right in challenger:
                if (
                    left.benchmark_id == right.benchmark_id
                    and left.target_start_year == right.target_start_year
                    and left.target_end_year == right.target_end_year
                ):
                    pairs.append((left, right))
        if not pairs:
            return None
        return max(
            pairs,
            key=lambda pair: (
                min(pair[0].as_of_year, pair[1].as_of_year),
                pair[0].target_end_year,
                pair[0].benchmark_id,
            ),
        )

    def compare(
        self,
        incumbent_id: str,
        challenger_id: str,
        *,
        year: int,
        standards: Sequence[MetricStandard],
    ) -> MethodComparison:
        incumbent = self._methods[incumbent_id]
        challenger = self._methods[challenger_id]
        if challenger.available_year > year:
            decision = HistoricalDecision.NOT_AVAILABLE
            return self._empty_comparison(incumbent_id, challenger_id, decision, "challenger not yet available")
        pair = self._comparable_pair(incumbent_id, challenger_id, year=year)
        if pair is None:
            return self._empty_comparison(
                incumbent_id,
                challenger_id,
                HistoricalDecision.INCOMPARABLE,
                "no identical forward benchmark window",
            )
        old, new = pair

        evidence_failures: list[str] = []
        if new.sample_count < self.policy.minimum_samples:
            evidence_failures.append("sample_count")
        if new.independent_replications < self.policy.minimum_replications:
            evidence_failures.append("independent_replications")
        if new.adversarial_runs < self.policy.minimum_adversarial_runs:
            evidence_failures.append("adversarial_runs")
        if (
            self.policy.require_verification_from_year is not None
            and year >= self.policy.require_verification_from_year
            and not new.verified
        ):
            evidence_failures.append("verification")

        invariant_failures = list(new.invariant_failures)
        metric_deltas: dict[str, float] = {}
        mandatory_failures: list[str] = []
        weighted = 0.0
        total_weight = 0.0
        improvements = 0
        for standard in standards:
            if standard.introduced_year > year:
                continue
            mandatory = (
                standard.mandatory_from_year is not None
                and year >= standard.mandatory_from_year
            )
            if standard.name not in old.metrics or standard.name not in new.metrics:
                if mandatory:
                    mandatory_failures.append(standard.name + ":missing")
                continue
            old_value = standard.orient(old.metrics[standard.name])
            new_value = standard.orient(new.metrics[standard.name])
            delta = new_value - old_value
            metric_deltas[standard.name] = delta
            if standard.minimum_candidate is not None:
                threshold = standard.orient(standard.minimum_candidate)
                if mandatory and new_value < threshold:
                    mandatory_failures.append(standard.name + ":below_minimum")
            if delta < -standard.maximum_regression and mandatory:
                mandatory_failures.append(standard.name + ":regression")
            if delta >= standard.minimum_improvement:
                improvements += 1
            weighted += standard.weight * delta
            total_weight += standard.weight
        weighted_gain = weighted / total_weight if total_weight else 0.0
        complexity_delta = max(0, challenger.complexity_rank - incumbent.complexity_rank)
        adjusted = weighted_gain - self.policy.complexity_penalty * complexity_delta

        rationale: list[str] = []
        if invariant_failures:
            decision = HistoricalDecision.INVARIANT_REJECTED
            rationale.append("challenger violates recorded invariants")
        elif mandatory_failures:
            decision = HistoricalDecision.INVARIANT_REJECTED
            rationale.append("mandatory metric gate failed")
        elif evidence_failures:
            decision = HistoricalDecision.SHADOW
            rationale.append("challenger remains shadow-only pending stronger evidence")
        elif adjusted > self.policy.minimum_weighted_gain and improvements:
            decision = HistoricalDecision.PROMOTE
            rationale.append("challenger improves the comparable historical frontier")
        else:
            decision = HistoricalDecision.HOLD
            rationale.append("incumbent retained after complexity-adjusted comparison")

        fingerprint = stable_fingerprint(
            {
                "year": year,
                "incumbent": incumbent_id,
                "challenger": challenger_id,
                "benchmark": old.benchmark_id,
                "old": old.custody_fingerprint,
                "new": new.custody_fingerprint,
                "deltas": metric_deltas,
                "weighted": weighted_gain,
                "adjusted": adjusted,
                "mandatory": mandatory_failures,
                "evidence": evidence_failures,
                "invariants": invariant_failures,
                "decision": decision.value,
            }
        )
        return MethodComparison(
            incumbent_id=incumbent_id,
            challenger_id=challenger_id,
            benchmark_id=old.benchmark_id,
            weighted_gain=weighted_gain,
            complexity_adjusted_gain=adjusted,
            metric_deltas=metric_deltas,
            mandatory_failures=tuple(sorted(set(mandatory_failures))),
            evidence_failures=tuple(sorted(set(evidence_failures))),
            invariant_failures=tuple(sorted(set(invariant_failures))),
            decision=decision,
            rationale=tuple(rationale),
            fingerprint=fingerprint,
        )

    @staticmethod
    def _empty_comparison(
        incumbent_id: str,
        challenger_id: str,
        decision: HistoricalDecision,
        reason: str,
    ) -> MethodComparison:
        fingerprint = stable_fingerprint(
            {
                "incumbent": incumbent_id,
                "challenger": challenger_id,
                "decision": decision.value,
                "reason": reason,
            }
        )
        return MethodComparison(
            incumbent_id,
            challenger_id,
            None,
            0.0,
            0.0,
            {},
            (),
            (),
            (),
            decision,
            (reason,),
            fingerprint,
        )

    def advance(
        self,
        facet: ScientificFacet,
        *,
        start_year: int,
        end_year: int,
        standards: Sequence[MetricStandard],
    ) -> tuple[YearFacetFrontier, ...]:
        """Replay the frontier year by year and reconsider maturing challengers.

        Eligibility and promotion are intentionally separate. A method can exist
        for years in shadow mode until enough forward evidence accumulates. At
        most one challenger is promoted in a given year: the strongest
        complexity-adjusted candidate against the incumbent at the start of that
        year. This removes iteration-order effects.
        """
        if end_year < start_year:
            raise AgentContractError("end_year precedes start_year")
        active: str | None = None
        role_map: dict[str, set[SurvivorRole]] = {}
        reports: list[YearFacetFrontier] = []

        for year in range(start_year, end_year + 1):
            eligible = self.methods(facet, through_year=year)
            if active is None and eligible:
                active = eligible[0].method_id
                role_map.setdefault(active, set()).add(SurvivorRole.ACTIVE)

            comparisons: list[MethodComparison] = []
            promotable: list[tuple[float, int, str, MethodComparison]] = []
            incumbent_at_start = active
            if incumbent_at_start is not None:
                for challenger in eligible:
                    if challenger.method_id == incumbent_at_start:
                        continue
                    comparison = self.compare(
                        incumbent_at_start,
                        challenger.method_id,
                        year=year,
                        standards=standards,
                    )
                    comparisons.append(comparison)
                    if comparison.decision is HistoricalDecision.PROMOTE:
                        promotable.append(
                            (
                                comparison.complexity_adjusted_gain,
                                -challenger.complexity_rank,
                                challenger.method_id,
                                comparison,
                            )
                        )
                    elif comparison.decision is HistoricalDecision.SHADOW:
                        role_map.setdefault(challenger.method_id, set()).add(
                            SurvivorRole.SHADOW
                        )
                    elif comparison.decision in {
                        HistoricalDecision.INVARIANT_REJECTED,
                        HistoricalDecision.LEAKAGE_REJECTED,
                    }:
                        role_map.setdefault(challenger.method_id, set()).add(
                            SurvivorRole.REJECTED
                        )
                    elif comparison.decision is HistoricalDecision.HOLD:
                        role_map.setdefault(challenger.method_id, set()).update(
                            challenger.survives_as
                        )

            if promotable and incumbent_at_start is not None:
                _, _, winner_id, _ = max(
                    promotable,
                    key=lambda row: (row[0], row[1], row[2]),
                )
                old = incumbent_at_start
                role_map.setdefault(old, set()).discard(SurvivorRole.ACTIVE)
                role_map.setdefault(old, set()).update(self._methods[old].survives_as)
                active = winner_id
                winner_roles = role_map.setdefault(winner_id, set())
                winner_roles.discard(SurvivorRole.SHADOW)
                winner_roles.discard(SurvivorRole.REJECTED)
                winner_roles.add(SurvivorRole.ACTIVE)

            survivor_roles = {
                method_id: tuple(sorted(roles, key=lambda role: role.value))
                for method_id, roles in sorted(role_map.items())
            }
            fingerprint = stable_fingerprint(
                {
                    "year": year,
                    "facet": facet.value,
                    "active": active,
                    "eligible": [item.method_id for item in eligible],
                    "roles": {
                        key: [role.value for role in roles]
                        for key, roles in survivor_roles.items()
                    },
                    "comparisons": [item.fingerprint for item in comparisons],
                }
            )
            reports.append(
                YearFacetFrontier(
                    year=year,
                    facet=facet,
                    active_method_id=active,
                    eligible_method_ids=tuple(item.method_id for item in eligible),
                    survivor_roles=survivor_roles,
                    comparisons=tuple(comparisons),
                    fingerprint=fingerprint,
                )
            )
        return tuple(reports)


def default_historical_methods() -> tuple[HistoricalMethod, ...]:
    """Curated lineage anchors; not a claim to enumerate all scientific work."""

    rows = (
        # Probability / uncertainty
        ("pascal_fermat_chance", 1654, "Classical chance calculus", ScientificFacet.PROBABILITY,
         "Enumerate equally possible outcomes when symmetry is defensible", EvidenceGrade.FOUNDATIONAL, 1),
        ("bayesian_updating", 1763, "Bayesian updating", ScientificFacet.PROBABILITY,
         "Update uncertainty by conditioning prior beliefs on evidence", EvidenceGrade.FOUNDATIONAL, 2),
        ("laplace_probability", 1812, "Laplace probability synthesis", ScientificFacet.PROBABILITY,
         "Combine inverse probability, symmetry and predictive reasoning", EvidenceGrade.FOUNDATIONAL, 2),
        ("kolmogorov_axioms", 1933, "Kolmogorov probability axioms", ScientificFacet.PROBABILITY,
         "Keep additive probability semantics explicit and internally coherent", EvidenceGrade.FOUNDATIONAL, 2),
        ("dempster_shafer", 1976, "Dempster-Shafer evidence theory", ScientificFacet.UNCERTAINTY,
         "Represent belief and plausibility without collapsing ignorance to a point probability", EvidenceGrade.FOUNDATIONAL, 4),
        ("possibility_theory", 1978, "Possibility theory", ScientificFacet.UNCERTAINTY,
         "Represent ordinal/upper uncertainty when additive priors are unjustified", EvidenceGrade.FOUNDATIONAL, 3),
        ("conformal_prediction", 1998, "Conformal prediction", ScientificFacet.UNCERTAINTY,
         "Calibrate prediction sets with finite-sample coverage under exchangeability", EvidenceGrade.REPLICATED, 5),
        ("conformal_risk_control", 2022, "Conformal risk control", ScientificFacet.UNCERTAINTY,
         "Control user-defined risks with calibration data rather than confidence rhetoric", EvidenceGrade.REPLICATED, 6),
        # Prediction
        ("markov_process", 1906, "Markov process", ScientificFacet.PREDICTIVE_MODELING,
         "Model state transitions with explicit conditional dependence", EvidenceGrade.FOUNDATIONAL, 2),
        ("kalman_filter", 1960, "Kalman filtering", ScientificFacet.PREDICTIVE_MODELING,
         "Maintain recursive state estimates with quantified process and observation noise", EvidenceGrade.FOUNDATIONAL, 4),
        ("box_jenkins", 1970, "Box-Jenkins ARIMA", ScientificFacet.PREDICTIVE_MODELING,
         "Diagnose, fit and validate stochastic time-series structure", EvidenceGrade.REPLICATED, 4),
        ("prequential_evaluation", 1984, "Prequential evaluation", ScientificFacet.PREDICTIVE_MODELING,
         "Judge forecasts in issuance order using only information available before outcomes", EvidenceGrade.FOUNDATIONAL, 4),
        ("garch", 1986, "GARCH", ScientificFacet.PREDICTIVE_MODELING,
         "Model conditional volatility rather than assuming constant predictive variance", EvidenceGrade.REPLICATED, 5),
        ("ensemble_boosting", 1996, "Boosting and ensemble prediction", ScientificFacet.PREDICTIVE_MODELING,
         "Combine weak or heterogeneous predictors while measuring out-of-sample error", EvidenceGrade.REPLICATED, 6),
        ("deep_probabilistic_forecasting", 2017, "Deep probabilistic forecasting", ScientificFacet.PREDICTIVE_MODELING,
         "Learn nonlinear conditional distributions while retaining probabilistic scoring", EvidenceGrade.EMPIRICAL, 8),
        ("forecast_foundation_models", 2023, "Forecast foundation models", ScientificFacet.PREDICTIVE_MODELING,
         "Transfer broad sequence priors while requiring chronological benchmark validation", EvidenceGrade.EMERGING, 10),
        # Memory / retrieval
        ("ebbinghaus_forgetting", 1885, "Forgetting and savings curves", ScientificFacet.MEMORY,
         "Treat retrievability as time- and exposure-dependent rather than static", EvidenceGrade.FOUNDATIONAL, 2),
        ("testing_effect", 1917, "Retrieval practice", ScientificFacet.MEMORY,
         "Successful retrieval changes later accessibility and should be measured separately from exposure", EvidenceGrade.REPLICATED, 3),
        ("complementary_learning_systems", 1995, "Complementary learning systems", ScientificFacet.MEMORY,
         "Separate fast episodic acquisition from slower consolidated knowledge", EvidenceGrade.REPLICATED, 6),
        ("prediction_error_memory", 2020, "Prediction-error memory updating", ScientificFacet.MEMORY,
         "Use violated expectations as a signal for memory updating without equating surprise with truth", EvidenceGrade.EMPIRICAL, 6),
        ("agent_episodic_memory", 2025, "Agent episodic memory", ScientificFacet.CONTEXT_RETRIEVAL,
         "Persist instance-specific interaction context and retrieve it before broad semantic reconstruction", EvidenceGrade.EMERGING, 7),
        ("spatiotemporal_agent_memory", 2026, "Spatial-temporal episodic agent memory", ScientificFacet.CONTEXT_RETRIEVAL,
         "Index events by temporal, entity and semantic cues for partial-cue and chronological retrieval", EvidenceGrade.EMERGING, 8),
        # Compiler / verification
        ("hoare_logic", 1969, "Hoare logic", ScientificFacet.VERIFICATION,
         "State program obligations as explicit pre/postconditions and invariants", EvidenceGrade.FOUNDATIONAL, 4),
        ("abstract_interpretation", 1977, "Abstract interpretation", ScientificFacet.PROGRAM_ANALYSIS,
         "Compute sound program properties over conservative abstract domains", EvidenceGrade.FOUNDATIONAL, 6),
        ("ssa", 1988, "Static single assignment", ScientificFacet.COMPILER,
         "Make def-use structure explicit to simplify dataflow reasoning and transformations", EvidenceGrade.FOUNDATIONAL, 5),
        ("proof_carrying_code", 1996, "Proof-carrying code", ScientificFacet.VERIFICATION,
         "Bind executable artifacts to independently checkable safety claims", EvidenceGrade.FORMALLY_VERIFIED, 8),
        ("compcert", 2006, "Verified compilation", ScientificFacet.COMPILER,
         "Use machine-checked semantic preservation where the proof envelope is tractable", EvidenceGrade.FORMALLY_VERIFIED, 10),
        ("mlir", 2019, "Multi-level IR", ScientificFacet.COMPILER,
         "Use explicit dialects, legality and progressive lowering across abstraction levels", EvidenceGrade.REPLICATED, 8),
        ("alive2", 2021, "Translation validation", ScientificFacet.VERIFICATION,
         "Validate concrete compiler transformations by checking source-target refinement", EvidenceGrade.REPLICATED, 9),
        ("backend_translation_validation", 2025, "Backend translation validation", ScientificFacet.COMPILER,
         "Extend refinement checking across lowering boundaries into machine-level code", EvidenceGrade.EMPIRICAL, 10),
        # Semantics / narrative / games
        ("defamiliarization", 1917, "Defamiliarization", ScientificFacet.SEMANTICS,
         "Model deliberate disruption of familiar priors as an interpretive signal", EvidenceGrade.FOUNDATIONAL, 2),
        ("kuleshov_montage", 1920, "Kuleshov juxtaposition", ScientificFacet.SEMANTICS,
         "Treat adjacent context as a possible cause of changed interpretation of an unchanged target", EvidenceGrade.EMPIRICAL, 3),
        ("focalization", 1972, "Narrative focalization", ScientificFacet.SEMANTICS,
         "Separate what is represented from what a viewpoint can know", EvidenceGrade.FOUNDATIONAL, 3),
        ("procedural_rhetoric", 2007, "Procedural rhetoric", ScientificFacet.GAME_REASONING,
         "Read rules and transition procedures as a distinct meaning-bearing channel", EvidenceGrade.EMPIRICAL, 4),
        ("empirical_montage_cognition", 2024, "Empirical montage cognition", ScientificFacet.SEMANTICS,
         "Test juxtaposition claims experimentally instead of treating film-theory coherence as proof", EvidenceGrade.EMPIRICAL, 6),
        # Control / planning / causality
        ("bellman_dynamic_programming", 1957, "Dynamic programming", ScientificFacet.CONTROL,
         "Decompose sequential decisions with recursive value structure", EvidenceGrade.FOUNDATIONAL, 4),
        ("astar", 1968, "A* search", ScientificFacet.PLANNING,
         "Use admissible heuristics to focus search while preserving optimality conditions", EvidenceGrade.FOUNDATIONAL, 4),
        ("structural_causal_models", 1988, "Structural causal models", ScientificFacet.CAUSALITY,
         "Separate observation from intervention and encode causal assumptions explicitly", EvidenceGrade.FOUNDATIONAL, 7),
        ("mcts", 2006, "Monte Carlo tree search", ScientificFacet.PLANNING,
         "Allocate simulation effort adaptively across large decision trees", EvidenceGrade.REPLICATED, 7),
        ("active_inference", 2010, "Active inference planning", ScientificFacet.METAREASONING,
         "Value actions partly for information gain while keeping preferences explicit", EvidenceGrade.EMPIRICAL, 8),
        ("causal_reinforcement_learning", 2020, "Causal reinforcement learning", ScientificFacet.CAUSALITY,
         "Exploit autonomous causal mechanisms and interventions for transfer and decision making", EvidenceGrade.EMERGING, 9),
    )
    # Chronological adjacency is not intellectual descent. Predecessor edges are
    # therefore left empty here unless a future curated record can justify a
    # specific inheritance/supersession claim.
    return tuple(
        HistoricalMethod(
            method_id=method_id,
            available_year=year,
            name=name,
            facet=facet,
            retained_principle=principle,
            evidence_grade=grade,
            complexity_rank=complexity,
        )
        for method_id, year, name, facet, principle, grade, complexity in rows
    )
