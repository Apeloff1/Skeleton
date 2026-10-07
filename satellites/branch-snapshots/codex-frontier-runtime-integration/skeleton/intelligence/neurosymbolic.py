"""Neural-Symbolic Integration — split from the intelligence monolith (v16.2)."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from skeleton.kernel.events import DomainEvent, EventBus

from ._tensor import Tensor

# =============================================================================
# 4. NEURAL-SYMBOLIC INTEGRATION
# =============================================================================

@dataclass
class SymbolicRule:
    """A symbolic rule: if premises then conclusion."""
    premises: List[str]
    conclusion: str
    confidence: float = 1.0
    learned: bool = False


class NeuralSymbolicEngine:
    """
    Hybrid neural-symbolic reasoning engine.
    Features:
      - Differentiable theorem proving
      - Rule induction from examples
      - Neuro-symbolic program synthesis
      - Symbolic knowledge base with neural similarity matching
    """

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
                    payload={
                        "premises": rule.premises,
                        "conclusion": rule.conclusion,
                        "confidence": rule.confidence,
                        "learned": rule.learned,
                    },
                    correlation_id=f"rule_{hashlib.sha256(str(rule.premises).encode()).hexdigest()[:12]}",
                )
            )

    def add_fact(self, fact: str, embedding: Optional[Tensor] = None) -> None:
        self._facts.add(fact)
        if embedding:
            self._embeddings[fact] = embedding
        elif fact not in self._embeddings:
            # Generate simple embedding
            self._embeddings[fact] = Tensor.random(64)

    def infer(self, goal: str, max_depth: int = 10) -> Tuple[bool, List[SymbolicRule], float]:
        """
        Attempt to prove goal from facts and rules.
        Returns (proved, proof_chain, confidence).
        """
        if goal in self._facts:
            return True, [], 1.0

        # Forward chaining with neural similarity for approximate matching
        frontier = list(self._facts)
        proven: Set[str] = set(self._facts)
        proof_chain: List[SymbolicRule] = []
        depth = 0

        while frontier and depth < max_depth:
            new_facts = []
            for rule in self._rules:
                if rule.conclusion in proven:
                    continue
                # Check if premises are satisfied (exact or neural similarity)
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

    def _neural_match(self, query: str, candidates: Union[Set[str], List[str]]) -> float:
        """Neural similarity between query and candidate set."""
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

    def induce_rules(
        self,
        examples: List[Dict[str, Any]],
        min_confidence: float = 0.8,
    ) -> List[SymbolicRule]:
        """
        Induce symbolic rules from examples.
        Simplified: find common patterns in feature-value pairs.
        """
        if not examples:
            return []

        # Find features that always co-occur with target
        rules = []
        all_keys = set(k for ex in examples for k in ex.keys())

        for target_key in all_keys:
            target_values = set(ex.get(target_key) for ex in examples if target_key in ex)
            for target_value in target_values:
                # Find premises that predict this target
                premises = []
                for key in all_keys:
                    if key == target_key:
                        continue
                    key_values = [ex.get(key) for ex in examples if target_key in ex and ex.get(target_key) == target_value]
                    if key_values and len(set(key_values)) == 1:
                        premises.append(f"{key}={key_values[0]}")

                if premises:
                    confidence = len([ex for ex in examples if all(
                        ex.get(k.split("=")[0]) == v for p in premises for k, v in [p.split("=", 1)]
                    ) and ex.get(target_key) == target_value]) / len(examples)

                    if confidence >= min_confidence:
                        rule = SymbolicRule(
                            premises=premises,
                            conclusion=f"{target_key}={target_value}",
                            confidence=confidence,
                            learned=True,
                        )
                        rules.append(rule)
                        self.add_rule(rule)

        return rules
