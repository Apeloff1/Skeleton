"""Counterfactual engine — "what if" reasoning over the causal graph.

The causal module estimates effects from observations; this engine answers
the harder question: given *this specific* observation, what would the
outcome have been under a different intervention? That is the third rung
of Pearl's ladder (association → intervention → counterfactual), and it is
what Jeeves needs to explain a pipeline failure as "the economy stage
broke because the scarcity parameter was 0, not 0.3" rather than "something
correlated with failure".

Method (abduction–action–prediction):
  1. **Abduction** — infer the exogenous noise terms that explain the
     observed outcome, under a linear additive-noise structural model.
  2. **Action** — apply the intervention: set the do-variables, severing
     their parent edges.
  3. **Prediction** — propagate forward through the structural equations
     with the *same* noise terms, producing the counterfactual outcome.

The structural model is linear with per-variable noise, estimated from the
observation history already stored in CausalInference — no new data
requirements, and fully deterministic given the same observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.errors import PipelineError
from skeleton.kernel.events import DomainEvent, EventBus

from .causal import CausalGraph


class CounterfactualError(PipelineError):
    code = "PPL.COUNTERFACTUAL"
    http_status = 422


@dataclass
class StructuralModel:
    """
    Linear additive-noise structural equations fitted to a causal graph.

    For each variable v:  v = bias_v + Σ_p coef[v][p] * p + noise_v
    Coefficients are estimated per-variable from observations by simple
    mean-difference fitting (no linear algebra dependency).
    """

    graph: CausalGraph
    coefficients: Dict[str, Dict[str, float]] = field(default_factory=dict)
    biases: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def fit(cls, graph: CausalGraph,
            observations: List[Dict[str, Any]]) -> "StructuralModel":
        if not observations:
            raise CounterfactualError("cannot fit a structural model with no observations")
        model = cls(graph=graph)
        for name, var in graph.variables.items():
            numeric = [o for o in observations
                       if isinstance(o.get(name), (int, float))]
            if not numeric:
                model.biases[name] = 0.0
                model.coefficients[name] = {}
                continue
            mean_v = sum(o[name] for o in numeric) / len(numeric)
            coefs: Dict[str, float] = {}
            bias = mean_v
            for parent in var.parents:
                # 1-D slope estimate: cov / var of the parent
                pairs = [(o.get(parent), o[name]) for o in numeric
                         if isinstance(o.get(parent), (int, float))]
                if len(pairs) < 2:
                    coefs[parent] = 0.0
                    continue
                xs = [p[0] for p in pairs]
                mean_x = sum(xs) / len(xs)
                var_x = sum((x - mean_x) ** 2 for x in xs) / (len(xs) - 1)
                cov = sum((x - mean_x) * (y - mean_v) for (x, y) in pairs) / (len(pairs) - 1)
                coefs[parent] = 0.0 if var_x == 0 else cov / var_x
                bias -= coefs[parent] * mean_x
            model.coefficients[name] = coefs
            model.biases[name] = bias
        return model

    def noise_terms(self, observation: Dict[str, Any]) -> Dict[str, float]:
        """Abduction: the exogenous noise that explains one observation."""
        noise: Dict[str, float] = {}
        for name in self.graph.variables:
            if not isinstance(observation.get(name), (int, float)):
                continue
            explained = self.biases.get(name, 0.0) + sum(
                c * observation.get(p, 0.0)
                for p, c in self.coefficients.get(name, {}).items()
            )
            noise[name] = observation[name] - explained
        return noise

    def predict(self, intervention: Dict[str, Any],
                noise: Dict[str, float]) -> Dict[str, float]:
        """Action + prediction: propagate under do(intervention)."""
        order = self._topological_order()
        values: Dict[str, float] = {}
        for name in order:
            if name in intervention:
                values[name] = float(intervention[name])
                continue
            values[name] = self.biases.get(name, 0.0) + sum(
                c * values.get(p, 0.0)
                for p, c in self.coefficients.get(name, {}).items()
            ) + noise.get(name, 0.0)
        return values

    def _topological_order(self) -> List[str]:
        order: List[str] = []
        remaining = dict(self.graph.variables)
        placed = set()
        while remaining:
            ready = [n for n, v in remaining.items()
                     if all(p in placed or p not in remaining for p in v.parents)]
            if not ready:
                raise CounterfactualError("causal graph contains a cycle")
            for name in sorted(ready):
                order.append(name)
                placed.add(name)
                del remaining[name]
        return order


class CounterfactualEngine:
    """Answers counterfactual queries against a fitted structural model."""

    def __init__(self, model: StructuralModel,
                 *, bus: Optional[EventBus] = None) -> None:
        self.model = model
        self._bus = bus
        self._queries = 0

    def what_if(
        self,
        observation: Dict[str, Any],
        intervention: Dict[str, Any],
        *,
        outcomes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Full abduction–action–prediction for one observation.
        Returns the counterfactual world plus the per-outcome delta vs.
        what was actually observed.
        """
        for var in intervention:
            if var not in self.model.graph.variables:
                raise CounterfactualError(
                    "intervention targets unknown variable",
                    context={"variable": var},
                )
        noise = self.model.noise_terms(observation)
        world = self.model.predict(intervention, noise)
        targets = outcomes or list(world)
        deltas = {
            name: world[name] - observation[name]
            for name in targets
            if name in world and isinstance(observation.get(name), (int, float))
        }
        self._queries += 1
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="intelligence.counterfactual.computed",
                    payload={
                        "intervention": intervention,
                        "outcomes": targets,
                        "deltas": {k: round(v, 4) for k, v in deltas.items()},
                    },
                    correlation_id=f"cf_{self._queries}",
                )
            )
        return {
            "intervention": intervention,
            "counterfactual": world,
            "observed": {k: observation.get(k) for k in targets},
            "deltas": deltas,
        }
