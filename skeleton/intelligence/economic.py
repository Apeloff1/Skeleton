"""Economic optimisation and cost-aware cascade planning.

The economic layer owns model metadata, hard budget/capability constraints and
batch allocation.  Online query difficulty and confidence escalation belong to
:mod:`skeleton.intelligence.cascade`; this module can now build a cascade from
one economic model registry instead of maintaining a second routing policy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Set

from skeleton.intelligence.cascade import CascadeRouter, ModelFn, _bad_cost, _bad_unit
from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class ModelOption:
    """A model option with cost and quality characteristics."""

    model_id: str
    cost_per_token: float
    quality_score: float  # 0-1, higher is better
    latency_ms: float
    capabilities: Set[str] = field(default_factory=set)


@dataclass
class BudgetConstraint:
    """Budget allocation constraints."""

    total_budget: float
    max_cost_per_query: float
    min_quality: float
    max_latency_ms: float


@dataclass(frozen=True)
class CascadePlan:
    """Economic model pair and accounting inputs for a ``CascadeRouter``."""

    cheap_model_id: str
    strong_model_id: str
    token_estimate: int
    cheap_cost: float
    strong_cost: float
    route_threshold: float
    escalate_below: float

    @property
    def single_model(self) -> bool:
        return self.cheap_model_id == self.strong_model_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cheap_model_id": self.cheap_model_id,
            "strong_model_id": self.strong_model_id,
            "token_estimate": self.token_estimate,
            "cheap_cost": self.cheap_cost,
            "strong_cost": self.strong_cost,
            "route_threshold": self.route_threshold,
            "escalate_below": self.escalate_below,
            "single_model": self.single_model,
        }


class EconomicOptimiser:
    """Token-cost optimiser with one registry shared by batch and cascade routing.

    ``route_query`` remains the legacy planning API for callers that already
    provide a complexity score.  New online callers should prefer
    ``plan_cascade``/``build_cascade_router`` so query difficulty is estimated
    exactly once by :class:`CascadeRouter` and confidence escalation remains
    part of that same decision path.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._models: Dict[str, ModelOption] = {}
        self._history: List[Dict[str, Any]] = []
        self._bus = bus

    def register_model(self, model: ModelOption) -> None:
        if not isinstance(model.model_id, str) or not model.model_id.strip():
            raise ValueError("model_id is required")
        if model.model_id in self._models:
            raise ValueError("model already registered")
        if _bad_cost(model.cost_per_token) or _bad_cost(model.latency_ms) or _bad_unit(model.quality_score):
            raise ValueError("model cost, latency, and quality must be finite")
        if not isinstance(model.capabilities, set):
            raise ValueError("capabilities must be a set")
        self._models[model.model_id] = model

    def compute_pareto_frontier(self) -> List[ModelOption]:
        """Return models not dominated on cost, quality and latency."""

        models = list(self._models.values())
        pareto: List[ModelOption] = []
        for model in models:
            dominated = False
            for other in models:
                if other.model_id == model.model_id:
                    continue
                if (
                    other.cost_per_token <= model.cost_per_token
                    and other.quality_score >= model.quality_score
                    and other.latency_ms <= model.latency_ms
                    and (
                        other.cost_per_token < model.cost_per_token
                        or other.quality_score > model.quality_score
                        or other.latency_ms < model.latency_ms
                    )
                ):
                    dominated = True
                    break
            if not dominated:
                pareto.append(model)
        return sorted(pareto, key=lambda model: (model.cost_per_token, model.model_id))

    @staticmethod
    def _validate_token_estimate(token_estimate: int) -> None:
        if type(token_estimate) is not int or token_estimate <= 0:
            raise ValueError("token_estimate must be a positive integer")

    @staticmethod
    def _effective_query_budget(constraint: BudgetConstraint) -> float:
        return min(constraint.total_budget, constraint.max_cost_per_query)

    @staticmethod
    def _estimated_cost(model: ModelOption, token_estimate: int) -> float:
        return model.cost_per_token * token_estimate

    def _eligible_models(
        self,
        *,
        required_capabilities: Set[str],
        constraint: BudgetConstraint,
        token_estimate: int,
    ) -> List[ModelOption]:
        budget = self._effective_query_budget(constraint)
        if budget < 0:
            return []
        return [
            model
            for model in self._models.values()
            if model.quality_score >= constraint.min_quality
            and model.latency_ms <= constraint.max_latency_ms
            and required_capabilities.issubset(model.capabilities)
            and self._estimated_cost(model, token_estimate) <= budget
        ]

    def _record_route(
        self,
        *,
        model: ModelOption,
        query_complexity: float,
        token_estimate: int,
        estimated_cost: float,
    ) -> None:
        event = {
            "model_id": model.model_id,
            "query_complexity": query_complexity,
            "token_estimate": token_estimate,
            "cost": estimated_cost,
            "quality_score": model.quality_score,
        }
        self._history.append(event)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="economic.query.routed",
                    payload=dict(event),
                    correlation_id=f"econ_{model.model_id}_{int(time.time())}",
                )
            )

    def route_query(
        self,
        query_complexity: float,
        required_capabilities: Set[str],
        constraint: BudgetConstraint,
        *,
        token_estimate: int = 1000,
    ) -> Optional[ModelOption]:
        """Choose a model for pre-scored/batch work under hard constraints.

        ``token_estimate`` is explicit so allocation and routing account for the
        same workload.  The historical 1000-token default is retained for
        compatibility.
        """

        self._validate_token_estimate(token_estimate)
        if isinstance(query_complexity, bool) or not isinstance(query_complexity, (int, float)) or not 0.0 <= float(query_complexity) <= 1.0:
            raise ValueError("query_complexity must be in [0, 1]")
        complexity = float(query_complexity)
        candidates = self._eligible_models(
            required_capabilities=required_capabilities,
            constraint=constraint,
            token_estimate=token_estimate,
        )
        if not candidates:
            return None

        max_cost = max(model.cost_per_token for model in candidates)

        def score(model: ModelOption) -> float:
            normalized_cost = (
                1.0 - (model.cost_per_token / max_cost) if max_cost > 0 else 1.0
            )
            return complexity * model.quality_score + (1.0 - complexity) * normalized_cost

        best = max(
            candidates,
            key=lambda model: (
                score(model),
                model.quality_score,
                -model.cost_per_token,
                -model.latency_ms,
                model.model_id,
            ),
        )
        estimated_cost = self._estimated_cost(best, token_estimate)
        self._record_route(
            model=best,
            query_complexity=complexity,
            token_estimate=token_estimate,
            estimated_cost=estimated_cost,
        )
        return best

    def plan_cascade(
        self,
        required_capabilities: Set[str],
        constraint: BudgetConstraint,
        *,
        token_estimate: int = 1000,
        route_threshold: float = 0.7,
        escalate_below: float = 0.55,
    ) -> Optional[CascadePlan]:
        """Select an economically valid cheap/strong pair for online routing.

        Hard constraints are applied before either model can enter the cascade.
        The cheap role is the least expensive eligible model; the strong role is
        the highest-quality eligible model.  Query difficulty is deliberately
        *not* scored here — ``CascadeRouter`` owns that signal.
        """

        self._validate_token_estimate(token_estimate)
        if _bad_unit(route_threshold) or _bad_unit(escalate_below):
            raise ValueError("thresholds must be in [0, 1]")

        candidates = self._eligible_models(
            required_capabilities=required_capabilities,
            constraint=constraint,
            token_estimate=token_estimate,
        )
        if not candidates:
            return None

        cheap = min(
            candidates,
            key=lambda model: (
                model.cost_per_token,
                -model.quality_score,
                model.latency_ms,
                model.model_id,
            ),
        )
        strong = max(
            candidates,
            key=lambda model: (
                model.quality_score,
                -model.latency_ms,
                -model.cost_per_token,
                model.model_id,
            ),
        )
        return CascadePlan(
            cheap_model_id=cheap.model_id,
            strong_model_id=strong.model_id,
            token_estimate=token_estimate,
            cheap_cost=self._estimated_cost(cheap, token_estimate),
            strong_cost=self._estimated_cost(strong, token_estimate),
            route_threshold=route_threshold,
            escalate_below=escalate_below,
        )

    def build_cascade_router(
        self,
        model_functions: Mapping[str, ModelFn],
        required_capabilities: Set[str],
        constraint: BudgetConstraint,
        *,
        token_estimate: int = 1000,
        route_threshold: float = 0.7,
        escalate_below: float = 0.55,
    ) -> Optional[CascadeRouter]:
        """Build a ``CascadeRouter`` using this optimiser's model registry.

        Missing runtime callables are configuration errors rather than routing
        misses, so they raise ``KeyError``.  A lack of economically eligible
        models returns ``None`` just like ``route_query``.
        """

        plan = self.plan_cascade(
            required_capabilities,
            constraint,
            token_estimate=token_estimate,
            route_threshold=route_threshold,
            escalate_below=escalate_below,
        )
        if plan is None:
            return None

        try:
            cheap_fn = model_functions[plan.cheap_model_id]
            strong_fn = model_functions[plan.strong_model_id]
        except KeyError as exc:
            raise KeyError(f"missing callable for economic model {exc.args[0]!r}") from exc

        return CascadeRouter(
            cheap_fn,
            strong_fn,
            route_threshold=plan.route_threshold,
            escalate_below=plan.escalate_below,
            cheap_cost=plan.cheap_cost,
            strong_cost=plan.strong_cost,
            cheap_name=plan.cheap_model_id,
            strong_name=plan.strong_model_id,
        )

    def allocate_budget(
        self,
        queries: List[Dict[str, Any]],
        constraint: BudgetConstraint,
    ) -> Dict[str, List[str]]:
        """Allocate a total budget across query work, highest complexity first."""

        allocation: Dict[str, List[str]] = {model_id: [] for model_id in self._models}
        remaining_budget = constraint.total_budget
        sorted_queries = sorted(
            queries,
            key=lambda query: query.get("complexity", 0.5),
            reverse=True,
        )

        for query in sorted_queries:
            if remaining_budget <= 0:
                break
            token_estimate = query.get("token_estimate", 1000)
            self._validate_token_estimate(token_estimate)
            model = self.route_query(
                query.get("complexity", 0.5),
                set(query.get("capabilities", [])),
                BudgetConstraint(
                    total_budget=remaining_budget,
                    max_cost_per_query=min(constraint.max_cost_per_query, remaining_budget),
                    min_quality=constraint.min_quality,
                    max_latency_ms=constraint.max_latency_ms,
                ),
                token_estimate=token_estimate,
            )
            if model:
                estimated_cost = self._estimated_cost(model, token_estimate)
                allocation[model.model_id].append(query["id"])
                remaining_budget -= estimated_cost

        return allocation

    def get_cost_statistics(self) -> Dict[str, Any]:
        """Return statistics for successful legacy/batch route decisions."""

        if not self._history:
            return {"queries": 0, "total_cost": 0.0}

        total_cost = sum(history["cost"] for history in self._history)
        return {
            "queries": len(self._history),
            "total_cost": total_cost,
            "average_cost": total_cost / len(self._history),
            "models_used": len({history["model_id"] for history in self._history}),
        }


__all__ = [
    "ModelOption",
    "BudgetConstraint",
    "CascadePlan",
    "EconomicOptimiser",
]
