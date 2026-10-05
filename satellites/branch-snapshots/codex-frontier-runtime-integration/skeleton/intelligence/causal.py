"""Causal Inference — split from the intelligence monolith (v16.2)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from skeleton.kernel.events import DomainEvent, EventBus

# =============================================================================
# 2. CAUSAL INFERENCE
# =============================================================================

@dataclass
class CausalVariable:
    """A variable in a causal model."""
    name: str
    values: List[Any]
    parents: List[str] = field(default_factory=list)


@dataclass
class CausalGraph:
    """A directed acyclic graph representing causal relationships."""
    variables: Dict[str, CausalVariable] = field(default_factory=dict)
    edges: List[Tuple[str, str]] = field(default_factory=list)  # (cause, effect)

    def add_edge(self, cause: str, effect: str) -> None:
        if cause not in self.variables or effect not in self.variables:
            raise ValueError("Both variables must be defined")
        self.edges.append((cause, effect))
        self.variables[effect].parents.append(cause)

    def is_ancestor(self, potential_ancestor: str, node: str) -> bool:
        """Check if potential_ancestor is an ancestor of node."""
        visited = set()
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current == potential_ancestor:
                return True
            if current in visited:
                continue
            visited.add(current)
            for var_name, var in self.variables.items():
                if current in var.parents:
                    queue.append(var_name)
        return False

    def get_backdoor_paths(self, treatment: str, outcome: str) -> List[List[str]]:
        """
        Find all backdoor paths between treatment and outcome.
        A backdoor path is a path that starts with an arrow into treatment.
        """
        # Simplified: find all undirected paths and check if first edge is into treatment
        paths: List[List[str]] = []
        self._find_paths(treatment, outcome, [treatment], set(), paths)
        backdoor = [p for p in paths if len(p) > 2 and p[1] in self.variables[treatment].parents]
        return backdoor

    def _find_paths(
        self,
        current: str,
        target: str,
        path: List[str],
        visited: Set[str],
        results: List[List[str]],
    ) -> None:
        if current == target and len(path) > 1:
            results.append(path.copy())
            return
        if current in visited:
            return
        visited.add(current)
        # Follow edges in both directions (for path finding)
        for cause, effect in self.edges:
            if cause == current and effect not in path:
                self._find_paths(effect, target, path + [effect], visited.copy(), results)
            if effect == current and cause not in path:
                self._find_paths(cause, target, path + [cause], visited.copy(), results)


class CausalInference:
    """
    Causal inference engine using Do-calculus and potential outcomes framework.
    Features:
      - Average Treatment Effect (ATE) estimation
      - Conditional Average Treatment Effect (CATE)
      - Counterfactual generation
      - Backdoor criterion adjustment
      - Instrumental variable estimation
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._graph: Optional[CausalGraph] = None
        self._data: List[Dict[str, Any]] = []
        self._bus = bus

    def set_graph(self, graph: CausalGraph) -> None:
        self._graph = graph

    def add_observation(self, observation: Dict[str, Any]) -> None:
        self._data.append(observation)

    def estimate_ate(
        self,
        treatment: str,
        outcome: str,
        *,
        adjustment_set: Optional[List[str]] = None,
    ) -> Tuple[float, float]:
        """
        Estimate Average Treatment Effect: E[Y(1)] - E[Y(0)]
        Returns (ate, standard_error).
        """
        if not self._data:
            return 0.0, 0.0

        # Determine adjustment set using backdoor criterion if not provided
        if adjustment_set is None and self._graph:
            adjustment_set = self._find_backdoor_adjustment(treatment, outcome)

        # Stratify by adjustment set and compute weighted difference
        strata: Dict[str, List[Dict[str, Any]]] = {}
        for obs in self._data:
            key = str(tuple(obs.get(c) for c in (adjustment_set or [])))
            strata.setdefault(key, []).append(obs)

        ate_weighted = 0.0
        total_weight = 0
        squared_errors = []

        for key, group in strata.items():
            treated = [obs for obs in group if obs.get(treatment) == 1]
            control = [obs for obs in group if obs.get(treatment) == 0]

            if not treated or not control:
                continue

            y_treated = sum(obs.get(outcome, 0) for obs in treated) / len(treated)
            y_control = sum(obs.get(outcome, 0) for obs in control) / len(control)
            stratum_ate = y_treated - y_control

            weight = len(group)
            ate_weighted += stratum_ate * weight
            total_weight += weight

            # Within-stratum variance
            var_treated = sum((obs.get(outcome, 0) - y_treated) ** 2 for obs in treated) / max(len(treated), 1)
            var_control = sum((obs.get(outcome, 0) - y_control) ** 2 for obs in control) / max(len(control), 1)
            stratum_var = var_treated / max(len(treated), 1) + var_control / max(len(control), 1)
            squared_errors.append(stratum_var * weight ** 2)

        if total_weight == 0:
            return 0.0, 0.0

        ate = ate_weighted / total_weight
        se = math.sqrt(sum(squared_errors)) / total_weight if squared_errors else 0.0

        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="causal.ate.estimated",
                    payload={
                        "treatment": treatment,
                        "outcome": outcome,
                        "ate": ate,
                        "se": se,
                        "strata": len(strata),
                    },
                    correlation_id=f"causal_{treatment}_{outcome}",
                )
            )

        return ate, se

    def _find_backdoor_adjustment(self, treatment: str, outcome: str) -> List[str]:
        """Find a valid backdoor adjustment set."""
        if not self._graph:
            return []
        # Simplified: return all parents of treatment that are not descendants of outcome
        candidates = self._graph.variables[treatment].parents.copy()
        # Remove descendants of outcome
        valid = [c for c in candidates if not self._graph.is_ancestor(outcome, c)]
        return valid

    def generate_counterfactual(
        self,
        observation: Dict[str, Any],
        intervention: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate a counterfactual: what if we had set variables differently?
        Uses deterministic imputation based on observed patterns.
        """
        counterfactual = observation.copy()
        for var, value in intervention.items():
            counterfactual[var] = value
            # Propagate effects through graph
            if self._graph:
                self._propagate_effects(counterfactual, var)
        return counterfactual

    def _propagate_effects(self, state: Dict[str, Any], changed_var: str) -> None:
        """Propagate causal effects through the graph."""
        if not self._graph:
            return
        # Find all descendants and update them
        for var_name, var in self._graph.variables.items():
            if changed_var in var.parents:
                # Simple imputation: average of observations with same parent values
                matching = [
                    obs for obs in self._data
                    if all(obs.get(p) == state.get(p) for p in var.parents)
                ]
                if matching:
                    state[var_name] = sum(obs.get(var_name, 0) for obs in matching) / len(matching)
