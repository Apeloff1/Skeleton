"""
================================================================================
skeleton.intelligence — Advanced Cognitive Systems (Part 2: Meta-Learning + Neuro-Symbolic + Economic Optimisation)
================================================================================
"""
from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.intelligence_part1 import Tensor


# =============================================================================
# 3. META-LEARNING
# =============================================================================

@dataclass
class TaskEmbedding:
    task_id: str
    embedding: Tensor
    support_set: List[Dict[str, Any]] = field(default_factory=list)
    query_set: List[Dict[str, Any]] = field(default_factory=list)


class MetaLearner:
    """Model-Agnostic Meta-Learning (MAML) style adaptation."""

    def __init__(self, parameter_dim: int = 128, bus: Optional[EventBus] = None) -> None:
        self.parameter_dim = parameter_dim
        self.meta_parameters = Tensor.random(parameter_dim)
        self.task_embeddings: Dict[str, TaskEmbedding] = {}
        self.learning_rate = 0.01
        self.inner_steps = 5
        self._bus = bus

    def embed_task(self, support_set: List[Dict[str, Any]], task_id: str) -> TaskEmbedding:
        if not support_set:
            embedding = Tensor.zeros(self.parameter_dim)
        else:
            features: List[List[float]] = []
            for example in support_set:
                numeric = [v for v in example.values() if isinstance(v, (int, float))]
                if numeric:
                    features.append(numeric)
            if not features:
                embedding = Tensor.zeros(self.parameter_dim)
            else:
                flat = [f for feat in features for f in feat]
                if len(flat) < self.parameter_dim:
                    flat.extend([0.0] * (self.parameter_dim - len(flat)))
                else:
                    flat = flat[:self.parameter_dim]
                embedding = Tensor(flat, (self.parameter_dim,))
        task_emb = TaskEmbedding(task_id=task_id, embedding=embedding, support_set=support_set)
        self.task_embeddings[task_id] = task_emb
        return task_emb

    def adapt(self, task_id: str, loss_fn: Callable[[Tensor, Dict[str, Any]], float]) -> Tensor:
        if task_id not in self.task_embeddings:
            raise ValueError(f"Task {task_id} not embedded")
        task = self.task_embeddings[task_id]
        params = Tensor(self.meta_parameters.data.copy(), self.meta_parameters.shape)
        for _ in range(self.inner_steps):
            if not task.support_set:
                break
            example = random.choice(task.support_set)
            loss = loss_fn(params, example)
            grad = self._numerical_gradient(params, lambda p: loss_fn(p, example))
            params = Tensor([p - self.learning_rate * g for p, g in zip(params.data, grad.data)], params.shape)
        if self._bus:
            final_loss = loss_fn(params, random.choice(task.support_set)) if task.support_set else 0
            self._bus.publish(
                DomainEvent(
                    topic="meta.adaptation.complete",
                    payload={"task_id": task_id, "inner_steps": self.inner_steps, "final_loss": final_loss},
                    correlation_id=f"meta_{task_id}",
                )
            )
        return params

    def _numerical_gradient(self, params: Tensor, loss_fn: Callable[[Tensor], float],
                            epsilon: float = 1e-5) -> Tensor:
        grad = []
        for i in range(len(params.data)):
            params_plus = Tensor(params.data.copy(), params.shape)
            params_plus.data[i] += epsilon
            params_minus = Tensor(params.data.copy(), params.shape)
            params_minus.data[i] -= epsilon
            grad.append((loss_fn(params_plus) - loss_fn(params_minus)) / (2 * epsilon))
        return Tensor(grad, params.shape)

    def transfer(self, source_task_id: str, target_task_id: str,
                 target_support: List[Dict[str, Any]]) -> Tensor:
        self.embed_task(target_support, target_task_id)
        source_params = self.adapt(source_task_id, lambda p, e: self._default_loss(p, e))
        self.meta_parameters = source_params
        return self.adapt(target_task_id, lambda p, e: self._default_loss(p, e))

    def _default_loss(self, params: Tensor, example: Dict[str, Any]) -> float:
        target = example.get("target", 0.0)
        features = [v for v in example.values() if isinstance(v, (int, float)) and v != target]
        if not features:
            return 0.0
        if len(features) < len(params.data):
            features.extend([0.0] * (len(params.data) - len(features)))
        else:
            features = features[:len(params.data)]
        prediction = sum(p * f for p, f in zip(params.data, features))
        return (prediction - target) ** 2


# =============================================================================
# 4. NEURAL-SYMBOLIC INTEGRATION
# =============================================================================

@dataclass
class SymbolicRule:
    premises: List[str]
    conclusion: str
    confidence: float = 1.0
    learned: bool = False


class NeuralSymbolicEngine:
    """Hybrid neural-symbolic reasoning engine."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._rules: List[SymbolicRule] = []
        self._facts: Set[str] = set()
        self._embeddings: Dict[str, Tensor] = {}
        self._bus = bus

    def add_rule(self, rule: SymbolicRule) -> None:
        self._rules.append(rule)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="neurosym.rule.added",
                    payload={"premises": rule.premises, "conclusion": rule.conclusion,
                             "confidence": rule.confidence, "learned": rule.learned},
                    correlation_id=f"rule_{hashlib.sha256(str(rule.premises).encode()).hexdigest()[:12]}",
                )
            )

    def add_fact(self, fact: str, embedding: Optional[Tensor] = None) -> None:
        self._facts.add(fact)
        if embedding:
            self._embeddings[fact] = embedding
        elif fact not in self._embeddings:
            self._embeddings[fact] = Tensor.random(64)

    def infer(self, goal: str, max_depth: int = 10) -> Tuple[bool, List[SymbolicRule], float]:
        if goal in self._facts:
            return True, [], 1.0
        frontier = list(self._facts)
        proven: Set[str] = set(self._facts)
        proof_chain: List[SymbolicRule] = []
        depth = 0
        while frontier and depth < max_depth:
            new_facts = []
            for rule in self._rules:
                if rule.conclusion in proven:
                    continue
                premise_satisfied = all(
                    p in proven or self._neural_match(p, proven) > 0.8
                    for p in rule.premises
                )
                if premise_satisfied:
                    new_facts.append(rule.conclusion)
                    proven.add(rule.conclusion)
                    proof_chain.append(rule)
                    if rule.conclusion == goal or self._neural_match(rule.conclusion, {goal}) > 0.9:
                        confidence = min(rule.confidence for rule in proof_chain) if proof_chain else 1.0
                        return True, proof_chain, confidence
            frontier = new_facts
            depth += 1
        return False, [], 0.0

    def _neural_match(self, query: str, candidates) -> float:
        if query not in self._embeddings:
            return 0.0
        query_emb = self._embeddings[query]
        best = 0.0
        for candidate in candidates:
            if candidate in self._embeddings:
                sim = self._cosine_similarity(query_emb.data, self._embeddings[candidate].data)
                best = max(best, sim)
        return best

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def induce_rules(self, examples: List[Dict[str, Any]],
                     min_confidence: float = 0.8) -> List[SymbolicRule]:
        if not examples:
            return []
        rules = []
        all_keys = set(k for ex in examples for k in ex.keys())
        for target_key in all_keys:
            target_values = set(ex.get(target_key) for ex in examples if target_key in ex)
            for target_value in target_values:
                premises = []
                for key in all_keys:
                    if key == target_key:
                        continue
                    key_values = [ex.get(key) for ex in examples
                                  if target_key in ex and ex.get(target_key) == target_value]
                    if key_values and len(set(key_values)) == 1:
                        premises.append(f"{key}={key_values[0]}")
                if premises:
                    confidence = len([ex for ex in examples if all(
                        ex.get(k.split("=")[0]) == v for p in premises for k, v in [p.split("=", 1)]
                    ) and ex.get(target_key) == target_value]) / len(examples)
                    if confidence >= min_confidence:
                        rule = SymbolicRule(premises=premises, conclusion=f"{target_key}={target_value}",
                                          confidence=confidence, learned=True)
                        rules.append(rule)
                        self.add_rule(rule)
        return rules


# =============================================================================
# 5. ECONOMIC OPTIMISATION
# =============================================================================

@dataclass
class ModelOption:
    model_id: str
    cost_per_token: float
    quality_score: float
    latency_ms: float
    capabilities: Set[str] = field(default_factory=set)


@dataclass
class BudgetConstraint:
    total_budget: float
    max_cost_per_query: float
    min_quality: float
    max_latency_ms: float


class EconomicOptimiser:
    """Token cost minimisation with quality preservation."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._models: Dict[str, ModelOption] = {}
        self._history: List[Dict[str, Any]] = []
        self._bus = bus

    def register_model(self, model: ModelOption) -> None:
        self._models[model.model_id] = model

    def compute_pareto_frontier(self) -> List[ModelOption]:
        models = list(self._models.values())
        pareto = []
        for m in models:
            dominated = False
            for other in models:
                if other.model_id == m.model_id:
                    continue
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

    def route_query(self, query_complexity: float, required_capabilities: Set[str],
                    constraint: BudgetConstraint) -> Optional[ModelOption]:
        candidates = [
            m for m in self._models.values()
            if m.quality_score >= constraint.min_quality
            and m.latency_ms <= constraint.max_latency_ms
            and required_capabilities.issubset(m.capabilities)
        ]
        if not candidates:
            return None
        def score(m: ModelOption) -> float:
            quality_weight = query_complexity
            cost_weight = 1 - query_complexity
            max_cost = max(c.cost_per_token for c in candidates)
            normalized_cost = 1 - (m.cost_per_token / max_cost) if max_cost > 0 else 1
            return quality_weight * m.quality_score + cost_weight * normalized_cost
        best = max(candidates, key=score)
        estimated_cost = best.cost_per_token * 1000
        if estimated_cost > constraint.max_cost_per_query:
            cheaper = [c for c in candidates if c.cost_per_token * 1000 <= constraint.max_cost_per_query]
            if cheaper:
                best = max(cheaper, key=lambda m: m.quality_score)
            else:
                return None
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="economic.query.routed",
                    payload={"model_id": best.model_id, "query_complexity": query_complexity,
                             "estimated_cost": estimated_cost, "quality_score": best.quality_score},
                    correlation_id=f"econ_{best.model_id}_{int(time.time())}",
                )
            )
        return best

    def allocate_budget(self, queries: List[Dict[str, Any]],
                        constraint: BudgetConstraint) -> Dict[str, List[str]]:
        allocation: Dict[str, List[str]] = {m: [] for m in self._models}
        remaining_budget = constraint.total_budget
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
        if not self._history:
            return {"queries": 0, "total_cost": 0.0}
        total_cost = sum(h.get("cost", 0) for h in self._history)
        return {
            "queries": len(self._history),
            "total_cost": total_cost,
            "average_cost": total_cost / len(self._history),
            "models_used": len(set(h.get("model_id") for h in self._history)),
        }


# =============================================================================
# INTELLIGENCE ORCHESTRATOR
# =============================================================================

class IntelligenceOrchestrator:
    """Composes all advanced intelligence systems into a unified interface."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        from skeleton.intelligence_part1 import TemporalReasoner, CausalInference
        self.temporal = TemporalReasoner(bus)
        self.causal = CausalInference(bus)
        self.meta = MetaLearner(bus=bus)
        self.neurosym = NeuralSymbolicEngine(bus)
        self.economic = EconomicOptimiser(bus)
        self._bus = bus

    def reason(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        results = {"temporal": None, "causal": None, "symbolic": None,
                   "economic": None, "confidence": 0.0}
        if context and "events" in context:
            for event_data in context["events"]:
                from skeleton.intelligence_part1 import TemporalEvent
                event = TemporalEvent(
                    event_id=event_data.get("id", str(hash(event_data))),
                    description=event_data.get("description", ""),
                    timestamp=event_data.get("timestamp", time.time()),
                    duration=event_data.get("duration"),
                )
                self.temporal.add_event(event)
            if context.get("predict_next"):
                predictions = self.temporal.predict_next(context["predict_next"])
                results["temporal"] = {"predictions": predictions}
        if context and "intervention" in context:
            treatment = context["intervention"].get("treatment")
            outcome = context["intervention"].get("outcome")
            if treatment and outcome:
                ate, se = self.causal.estimate_ate(treatment, outcome)
                results["causal"] = {"ate": ate, "se": se}
        if context and "goal" in context:
            proved, chain, confidence = self.neurosym.infer(context["goal"])
            results["symbolic"] = {"proved": proved, "chain": [r.conclusion for r in chain],
                                   "confidence": confidence}
        if context and "query_complexity" in context:
            model = self.economic.route_query(
                context["query_complexity"],
                set(context.get("required_capabilities", [])),
                BudgetConstraint(
                    total_budget=context.get("budget", 100.0),
                    max_cost_per_query=context.get("max_cost", 10.0),
                    min_quality=context.get("min_quality", 0.7),
                    max_latency_ms=context.get("max_latency", 5000),
                ),
            )
            if model:
                results["economic"] = {
                    "model_id": model.model_id, "cost": model.cost_per_token,
                    "quality": model.quality_score,
                }
        confidences = [v.get("confidence", 0) for v in results.values() if isinstance(v, dict)]
        results["confidence"] = sum(confidences) / len(confidences) if confidences else 0.0
        return results
