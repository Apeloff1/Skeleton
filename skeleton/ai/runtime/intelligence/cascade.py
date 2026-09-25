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

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class ModelResponse:
    """One model's answer with its self-reported confidence."""

    text: str
    confidence: float


ModelFn = Callable[[str], ModelResponse]


def difficulty_estimate(query: str) -> float:
    """0..1 difficulty from surface features — no model call required."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")
    q = query.strip()
    words = q.split()
    length_score = min(1.0, len(words) / 60.0)
    avg_len = sum(len(w) for w in words) / max(1, len(words))
    vocab_score = min(1.0, max(0.0, (avg_len - 4.5) / 4.0))
    structure = 0.0
    if any(c in q for c in "()[]{}:;"):
        structure += 0.25
    if "?" in q:
        structure += 0.15
    if any(
        w.lower()
        in {
            "prove",
            "derive",
            "optimize",
            "debug",
            "refactor",
            "architect",
            "formal",
            "theorem",
            "constraint",
        }
        for w in words
    ):
        structure += 0.35
    return min(1.0, 0.45 * length_score + 0.30 * vocab_score + structure)


@dataclass
class RouteDecision:
    model: str
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


def _bad_unit(value: float) -> bool:
    return isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0


def _bad_cost(value: float) -> bool:
    return isinstance(value, bool) or not isinstance(value, (int, float)) or not value >= 0 or value != value or value == float("inf")


def _usable(response: ModelResponse) -> bool:
    return (
        isinstance(response, ModelResponse)
        and isinstance(response.text, str)
        and bool(response.text.strip())
        and not _bad_unit(response.confidence)
    )


class CascadeRouter:
    """Cheap-first routing with difficulty pre-check and confidence escalation.

    ``cheap_name`` and ``strong_name`` default to the historical role labels,
    but callers that own a model registry can provide stable model IDs.  This
    keeps route telemetry aligned with economic/model-registry decisions while
    preserving the original API for existing callers.
    """

    def __init__(
        self,
        cheap: ModelFn,
        strong: ModelFn,
        *,
        route_threshold: float = 0.7,
        escalate_below: float = 0.55,
        cheap_cost: float = 1.0,
        strong_cost: float = 10.0,
        cheap_name: str = "cheap",
        strong_name: str = "strong",
    ) -> None:
        if _bad_unit(route_threshold) or _bad_unit(escalate_below):
            raise ValueError("thresholds must be in [0, 1]")
        if _bad_cost(cheap_cost) or _bad_cost(strong_cost):
            raise ValueError("model costs must be non-negative")
        if not cheap_name or not strong_name:
            raise ValueError("model names must be non-empty")

        self.cheap = cheap
        self.strong = strong
        self.route_threshold = route_threshold
        self.escalate_below = escalate_below
        self.cheap_cost = cheap_cost
        self.strong_cost = strong_cost
        self.cheap_name = cheap_name
        self.strong_name = strong_name
        self.decisions = 0
        self.escalations = 0
        self.strong_direct = 0
        self.total_cost = 0.0

    def route(self, query: str) -> RouteDecision:
        """Answer the query with the cheapest model that can handle it."""

        if not isinstance(query, str) or not query.strip():
            raise ValueError("query is required")
        difficulty = difficulty_estimate(query)

        if difficulty >= self.route_threshold:
            resp = self.strong(query)
            self.total_cost += self.strong_cost
            if not _usable(resp):
                raise ValueError("model did not answer")
            self.decisions += 1
            self.strong_direct += 1
            return RouteDecision(
                model=self.strong_name,
                text=resp.text,
                confidence=float(resp.confidence),
                escalated=False,
                difficulty=difficulty,
                reason="difficulty_threshold",
            )

        resp = self.cheap(query)
        self.total_cost += self.cheap_cost
        if _usable(resp) and float(resp.confidence) >= self.escalate_below:
            self.decisions += 1
            return RouteDecision(
                model=self.cheap_name,
                text=resp.text,
                confidence=float(resp.confidence),
                escalated=False,
                difficulty=difficulty,
                reason="cheap_confident",
            )

        resp = self.strong(query)
        self.total_cost += self.strong_cost
        if not _usable(resp):
            raise ValueError("model did not answer")
        self.decisions += 1
        self.escalations += 1
        return RouteDecision(
            model=self.strong_name,
            text=resp.text,
            confidence=float(resp.confidence),
            escalated=True,
            difficulty=difficulty,
            reason="confidence_escalation",
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
