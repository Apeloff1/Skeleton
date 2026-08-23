"""
================================================================================
skeleton.intelligence — Advanced Cognitive Systems (Part 1: Tensor + Temporal + Causal)
================================================================================
Quad-system intelligence substrate:
  1. Temporal Reasoning — time-aware inference, future-state prediction
  2. Causal Inference — Do-calculus for intervention analysis, counterfactuals
================================================================================
"""
from __future__ import annotations

import hashlib
import math
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from skeleton.kernel.events import DomainEvent, EventBus


# =============================================================================
# COMMON TENSOR INTERFACE
# =============================================================================

@dataclass
class Tensor:
    """Simple tensor for internal operations (no external deps)."""
    data: List[float]
    shape: Tuple[int, ...]
    grad: Optional[List[float]] = None

    def __post_init__(self):
        expected = math.prod(self.shape)
        if len(self.data) != expected:
            raise ValueError(f"Data length {len(self.data)} != shape product {expected}")

    @classmethod
    def zeros(cls, *shape: int) -> "Tensor":
        return cls(data=[0.0] * math.prod(shape), shape=shape)

    @classmethod
    def ones(cls, *shape: int) -> "Tensor":
        return cls(data=[1.0] * math.prod(shape), shape=shape)

    @classmethod
    def random(cls, *shape: int) -> "Tensor":
        return cls(data=[random.random() for _ in range(math.prod(shape))], shape=shape)

    def __add__(self, other: "Tensor") -> "Tensor":
        if self.shape != other.shape:
            raise ValueError("Shape mismatch")
        return Tensor([a + b for a, b in zip(self.data, other.data)], self.shape)

    def __mul__(self, scalar: float) -> "Tensor":
        return Tensor([a * scalar for a in self.data], self.shape)

    def dot(self, other: "Tensor") -> float:
        if len(self.data) != len(other.data):
            raise ValueError("Length mismatch")
        return sum(a * b for a, b in zip(self.data, other.data))

    def mean(self) -> float:
        return sum(self.data) / len(self.data) if self.data else 0.0

    def std(self) -> float:
        if len(self.data) < 2:
            return 0.0
        m = self.mean()
        variance = sum((x - m) ** 2 for x in self.data) / (len(self.data) - 1)
        return math.sqrt(variance)


# =============================================================================
# 1. TEMPORAL REASONING
# =============================================================================

@dataclass
class TemporalEvent:
    """An event with temporal anchoring."""
    event_id: str
    description: str
    timestamp: float
    duration: Optional[float] = None
    uncertainty: float = 0.0
    relations: Dict[str, str] = field(default_factory=dict)

    def before(self, other: "TemporalEvent") -> bool:
        return self.timestamp + self.uncertainty < other.timestamp - other.uncertainty

    def after(self, other: "TemporalEvent") -> bool:
        return other.before(self)

    def overlaps(self, other: "TemporalEvent") -> bool:
        if self.duration is None or other.duration is None:
            return False
        return (self.timestamp < other.timestamp + other.duration and
                other.timestamp < self.timestamp + self.duration)


class TemporalReasoner:
    """
    Time-aware inference engine.
    Features: chronology resolution, future-state prediction, Allen algebra.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._events: Dict[str, TemporalEvent] = {}
        self._patterns: List[List[str]] = []
        self._bus = bus

    def add_event(self, event: TemporalEvent) -> None:
        self._events[event.event_id] = event
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="temporal.event.added",
                    payload={"event_id": event.event_id, "timestamp": event.timestamp,
                             "description": event.description},
                    correlation_id=f"temp_{event.event_id}",
                )
            )

    def resolve_chronology(self, event_ids: List[str]) -> List[TemporalEvent]:
        events = [self._events[eid] for eid in event_ids if eid in self._events]
        return sorted(events, key=lambda e: (e.timestamp, -e.uncertainty))

    def predict_next(self, sequence: List[str], *, horizon: float = 3600,
                     confidence_threshold: float = 0.7) -> List[Tuple[str, float]]:
        if len(sequence) < 2:
            return []
        predictions: Dict[str, List[float]] = {}
        for pattern in self._patterns:
            if len(pattern) <= len(sequence):
                continue
            if pattern[:len(sequence)] == sequence:
                next_event = pattern[len(sequence)]
                confidence = 0.5 + 0.5 * (len(pattern) / (len(pattern) + 10))
                predictions.setdefault(next_event, []).append(confidence)
        result = [(eid, sum(confs) / len(confs))
                  for eid, confs in predictions.items()
                  if sum(confs) / len(confs) >= confidence_threshold]
        return sorted(result, key=lambda x: x[1], reverse=True)

    def allen_relation(self, a: TemporalEvent, b: TemporalEvent) -> str:
        if a.duration is None or b.duration is None:
            if a.timestamp < b.timestamp: return "before"
            elif a.timestamp > b.timestamp: return "after"
            else: return "equal"
        a_start, a_end = a.timestamp, a.timestamp + a.duration
        b_start, b_end = b.timestamp, b.timestamp + b.duration
        if a_end < b_start: return "before"
        elif a_end == b_start: return "meets"
        elif a_start < b_start and a_end > b_start and a_end < b_end: return "overlaps"
        elif a_start == b_start and a_end < b_end: return "starts"
        elif a_start > b_start and a_end < b_end: return "during"
        elif a_start > b_start and a_end == b_end: return "finishes"
        elif a_start == b_start and a_end == b_end: return "equal"
        elif a_start > b_end: return "after"
        elif a_start == b_end: return "met-by"
        elif b_start < a_start and b_end > a_start and b_end < a_end: return "overlapped-by"
        elif b_start == a_start and b_end > a_end: return "started-by"
        elif b_start < a_start and b_end > a_end: return "contains"
        elif b_start < a_start and b_end == a_end: return "finished-by"
        else: return "unknown"

    def query_temporal(self, query: str, *, time_window: Optional[Tuple[float, float]] = None
                       ) -> List[TemporalEvent]:
        results = []
        for event in self._events.values():
            if time_window and not (time_window[0] <= event.timestamp <= time_window[1]):
                continue
            if query.lower() in event.description.lower():
                results.append(event)
        return sorted(results, key=lambda e: e.timestamp)

    def learn_pattern(self, sequence: List[str]) -> None:
        if len(sequence) >= 2:
            self._patterns.append(sequence)
            if self._bus:
                self._bus.publish(
                    DomainEvent(
                        topic="temporal.pattern.learned",
                        payload={"sequence": sequence, "length": len(sequence)},
                        correlation_id=f"pattern_{hashlib.sha256(str(sequence).encode()).hexdigest()[:12]}",
                    )
                )


# =============================================================================
# 2. CAUSAL INFERENCE
# =============================================================================

@dataclass
class CausalVariable:
    name: str
    values: List[Any]
    parents: List[str] = field(default_factory=list)


@dataclass
class CausalGraph:
    variables: Dict[str, CausalVariable] = field(default_factory=dict)
    edges: List[Tuple[str, str]] = field(default_factory=list)

    def add_edge(self, cause: str, effect: str) -> None:
        if cause not in self.variables or effect not in self.variables:
            raise ValueError("Both variables must be defined")
        self.edges.append((cause, effect))
        self.variables[effect].parents.append(cause)

    def is_ancestor(self, potential_ancestor: str, node: str) -> bool:
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
        paths: List[List[str]] = []
        self._find_paths(treatment, outcome, [treatment], set(), paths)
        return [p for p in paths if len(p) > 2 and p[1] in self.variables[treatment].parents]

    def _find_paths(self, current: str, target: str, path: List[str],
                    visited: Set[str], results: List[List[str]]) -> None:
        if current == target and len(path) > 1:
            results.append(path.copy())
            return
        if current in visited:
            return
        visited.add(current)
        for cause, effect in self.edges:
            if cause == current and effect not in path:
                self._find_paths(effect, target, path + [effect], visited.copy(), results)
            if effect == current and cause not in path:
                self._find_paths(cause, target, path + [cause], visited.copy(), results)


class CausalInference:
    """
    Causal inference engine using Do-calculus and potential outcomes.
    Features: ATE estimation, counterfactuals, backdoor adjustment.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._graph: Optional[CausalGraph] = None
        self._data: List[Dict[str, Any]] = []
        self._bus = bus

    def set_graph(self, graph: CausalGraph) -> None:
        self._graph = graph

    def add_observation(self, observation: Dict[str, Any]) -> None:
        self._data.append(observation)

    def estimate_ate(self, treatment: str, outcome: str,
                     *, adjustment_set: Optional[List[str]] = None) -> Tuple[float, float]:
        if not self._data:
            return 0.0, 0.0
        if adjustment_set is None and self._graph:
            adjustment_set = self._find_backdoor_adjustment(treatment, outcome)

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
                    payload={"treatment": treatment, "outcome": outcome, "ate": ate, "se": se,
                             "strata": len(strata)},
                    correlation_id=f"causal_{treatment}_{outcome}",
                )
            )
        return ate, se

    def _find_backdoor_adjustment(self, treatment: str, outcome: str) -> List[str]:
        if not self._graph:
            return []
        candidates = self._graph.variables[treatment].parents.copy()
        return [c for c in candidates if not self._graph.is_ancestor(outcome, c)]

    def generate_counterfactual(self, observation: Dict[str, Any],
                                intervention: Dict[str, Any]) -> Dict[str, Any]:
        counterfactual = observation.copy()
        for var, value in intervention.items():
            counterfactual[var] = value
            if self._graph:
                self._propagate_effects(counterfactual, var)
        return counterfactual

    def _propagate_effects(self, state: Dict[str, Any], changed_var: str) -> None:
        if not self._graph:
            return
        for var_name, var in self._graph.variables.items():
            if changed_var in var.parents:
                matching = [obs for obs in self._data
                            if all(obs.get(p) == state.get(p) for p in var.parents)]
                if matching:
                    state[var_name] = sum(obs.get(var_name, 0) for obs in matching) / len(matching)
