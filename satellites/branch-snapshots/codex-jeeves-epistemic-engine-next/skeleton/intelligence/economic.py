"""Economic Optimisation — split from the intelligence monolith (v16.2)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from skeleton.kernel.events import DomainEvent, EventBus

# =============================================================================
# 5. ECONOMIC OPTIMISATION
# =============================================================================

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


class EconomicOptimiser:
    """
    Token cost minimisation with quality preservation.
    Features:
      - Pareto frontier computation for cost-quality tradeoffs
      - Budget allocation across model tiers
      - Dynamic model routing based on query complexity
      - Cost prediction and tracking
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._models: Dict[str, ModelOption] = {}
        self._history: List[Dict[str, Any]] = []
        self._bus = bus

    def register_model(self, model: ModelOption) -> None:
        self._models[model.model_id] = model

    def compute_pareto_frontier(self) -> List[ModelOption]:
        """
        Compute Pareto-optimal models (no other model is both cheaper and better).
        """
        models = list(self._models.values())
        pareto = []
        for m in models:
            dominated = False
            for other in models:
                if other.model_id == m.model_id:
                    continue
                # other dominates m if it's cheaper AND better quality AND faster
                if (other.cost_per_token <= m.cost_per_token and
                    other.quality_score >= m.quality_score and
                    other.latency_ms <= m.latency_ms and
                    (other.cost_per_token < m.cost_per_token or
                     other.quality_score > m.quality_score or
                     other.latency_ms < m.latency_ms)):
                    dominated = True
                    break
            if not dominated:
                pareto.append(m)
        return sorted(pareto, key=lambda m: m.cost_per_token)

    def route_query(
        self,
        query_complexity: float,  # 0-1
        required_capabilities: Set[str],
        constraint: BudgetConstraint,
    ) -> Optional[ModelOption]:
        """
        Route a query to the optimal model given constraints.
        """
        candidates = [
            m for m in self._models.values()
            if m.quality_score >= constraint.min_quality
            and m.latency_ms <= constraint.max_latency_ms
            and required_capabilities.issubset(m.capabilities)
        ]

        if not candidates:
            return None

        # Score by: quality / cost, weighted by query complexity
        # High complexity -> prefer quality; low complexity -> prefer cost
        def score(m: ModelOption) -> float:
            quality_weight = query_complexity
            cost_weight = 1 - query_complexity
            # Normalize cost (lower is better)
            max_cost = max(c.cost_per_token for c in candidates)
            normalized_cost = 1 - (m.cost_per_token / max_cost) if max_cost > 0 else 1
            return quality_weight * m.quality_score + cost_weight * normalized_cost

        best = max(candidates, key=score)

        # Check budget
        estimated_cost = best.cost_per_token * 1000  # Assume 1K tokens
        if estimated_cost > constraint.max_cost_per_query:
            # Fall back to cheaper option
            cheaper = [c for c in candidates if c.cost_per_token * 1000 <= constraint.max_cost_per_query]
            if cheaper:
                best = max(cheaper, key=lambda m: m.quality_score)
            else:
                return None

        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="economic.query.routed",
                    payload={
                        "model_id": best.model_id,
                        "query_complexity": query_complexity,
                        "estimated_cost": estimated_cost,
                        "quality_score": best.quality_score,
                    },
                    correlation_id=f"econ_{best.model_id}_{int(time.time())}",
                )
            )

        return best

    def allocate_budget(
        self,
        queries: List[Dict[str, Any]],
        constraint: BudgetConstraint,
    ) -> Dict[str, List[str]]:
        """
        Allocate budget across query types.
        Returns mapping: model_id -> list of query ids.
        """
        allocation: Dict[str, List[str]] = {m: [] for m in self._models}
        remaining_budget = constraint.total_budget

        # Sort queries by complexity (high first to ensure quality)
        sorted_queries = sorted(queries, key=lambda q: q.get("complexity", 0.5), reverse=True)

        for query in sorted_queries:
            if remaining_budget <= 0:
                break

            model = self.route_query(
                query.get("complexity", 0.5),
                set(query.get("capabilities", [])),
                BudgetConstraint(
                    total_budget=remaining_budget,
                    max_cost_per_query=min(constraint.max_cost_per_query, remaining_budget),
                    min_quality=constraint.min_quality,
                    max_latency_ms=constraint.max_latency_ms,
                ),
            )

            if model:
                estimated_cost = model.cost_per_token * query.get("token_estimate", 1000)
                allocation[model.model_id].append(query["id"])
                remaining_budget -= estimated_cost

        return allocation

    def get_cost_statistics(self) -> Dict[str, Any]:
        """Return cost tracking statistics."""
        if not self._history:
            return {"queries": 0, "total_cost": 0.0}

        total_cost = sum(h.get("cost", 0) for h in self._history)
        return {
            "queries": len(self._history),
            "total_cost": total_cost,
            "average_cost": total_cost / len(self._history),
            "models_used": len(set(h.get("model_id") for h in self._history)),
        }
