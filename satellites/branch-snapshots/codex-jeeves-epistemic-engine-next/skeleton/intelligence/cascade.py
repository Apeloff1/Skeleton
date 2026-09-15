"""Cascade router — difficulty-aware model routing with confidence escalation.

Wave-3 SOTA (RouteLLM / 2026 cascade surveys): the consistent result is
~95% of frontier quality at ~half the cost when easy queries stay on the
cheap model and only hard ones escalate. Two routing signals:

1. **Difficulty estimate** — lexical heuristics over the query (length,
   rare-token density, structural complexity) place it on a 0..1 scale;
   above ``route_threshold`` the query goes straight to the strong model.
2. **Self-confidence escalation** — the cheap model answers first; if its
   reported confidence falls below ``escalate_below``, the query escalates
   and the strong model answers instead. This is the cascade pattern's
   core trick: escalation is decided by the model, not guessed upfront.

Pure domain — models are callables, so the router is testable in CI with
fakes. Cost accounting is included so routing decisions are auditable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ModelResponse:
    """One model's answer with its self-reported confidence."""
    text: str
    confidence: float


ModelFn = Callable[[str], ModelResponse]


def difficulty_estimate(query: str) -> float:
    """0..1 difficulty from surface features — no model call required."""
    q = (query or "").strip()
    if not q:
        return 0.0
    words = q.split()
    length_score = min(1.0, len(words) / 60.0)
    avg_len = sum(len(w) for w in words) / max(1, len(words))
    vocab_score = min(1.0, max(0.0, (avg_len - 4.5) / 4.0))
    structure = 0.0
    if any(c in q for c in "()[]{}:;"):
        structure += 0.25
    if "?" in q:
        structure += 0.15
    if any(w.lower() in {"prove", "derive", "optimize", "debug", "refactor",
                         "architect", "formal", "theorem", "constraint"}
           for w in words):
        structure += 0.35
    return min(1.0, 0.45 * length_score + 0.30 * vocab_score + structure)


@dataclass
class RouteDecision:
    model: str                      # which model actually answered
    text: str
    confidence: float
    escalated: bool
    difficulty: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "confidence": round(self.confidence, 4),
            "escalated": self.escalated,
            "difficulty": round(self.difficulty, 4),
            "reason": self.reason,
        }


class CascadeRouter:
    """Cheap-first routing with difficulty pre-check and confidence escalation."""

    def __init__(
        self,
        cheap: ModelFn,
        strong: ModelFn,
        *,
        route_threshold: float = 0.7,
        escalate_below: float = 0.55,
        cheap_cost: float = 1.0,
        strong_cost: float = 10.0,
    ) -> None:
        self.cheap = cheap
        self.strong = strong
        self.route_threshold = route_threshold
        self.escalate_below = escalate_below
        self.cheap_cost = cheap_cost
        self.strong_cost = strong_cost
        self.decisions = 0
        self.escalations = 0
        self.strong_direct = 0
        self.total_cost = 0.0

    def route(self, query: str) -> RouteDecision:
        """Answer the query with the cheapest model that can handle it."""
        self.decisions += 1
        difficulty = difficulty_estimate(query)

        if difficulty >= self.route_threshold:
            self.strong_direct += 1
            self.total_cost += self.strong_cost
            resp = self.strong(query)
            return RouteDecision(
                model="strong", text=resp.text, confidence=resp.confidence,
                escalated=False, difficulty=difficulty, reason="difficulty_threshold",
            )

        self.total_cost += self.cheap_cost
        resp = self.cheap(query)
        if resp.confidence >= self.escalate_below:
            return RouteDecision(
                model="cheap", text=resp.text, confidence=resp.confidence,
                escalated=False, difficulty=difficulty, reason="cheap_confident",
            )

        self.escalations += 1
        self.total_cost += self.strong_cost
        resp = self.strong(query)
        return RouteDecision(
            model="strong", text=resp.text, confidence=resp.confidence,
            escalated=True, difficulty=difficulty, reason="confidence_escalation",
        )

    def stats(self) -> Dict[str, Any]:
        naive = self.decisions * self.strong_cost
        return {
            "decisions": self.decisions,
            "strong_direct": self.strong_direct,
            "escalations": self.escalations,
            "cheap_served": self.decisions - self.strong_direct - self.escalations,
            "total_cost": round(self.total_cost, 2),
            "cost_vs_all_strong": round(self.total_cost / naive, 4) if naive else 1.0,
        }
