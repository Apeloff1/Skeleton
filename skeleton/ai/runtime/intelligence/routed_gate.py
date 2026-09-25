"""Routed gate — uncertainty gating composed with cascade escalation.

The uncertainty gate decides ANSWER / ABSTAIN / ESCALATE from a candidate
set; the cascade router knows how to escalate cheap → strong. This module
closes the loop: sample candidates from the cheap model, gate them, and on
ESCALATE hand the query to the strong model through the cascade's own
difficulty bookkeeping — one call, full cost accounting.

Flow per query:

1. Difficulty pre-check (cascade): hard queries skip sampling entirely and
   go straight to strong.
2. Sample ``n`` candidates from the cheap model.
3. Gate them: ANSWER returns the modal best; ABSTAIN returns an honest
   non-answer with the gate's diagnostics; ESCALATE re-answers on strong.

Every decision is recorded so the routing's value is auditable
(cost vs all-strong, abstain rate, escalation rate).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .cascade import CascadeRouter, ModelResponse
from .uncertainty import Candidate, GateVerdict, UncertaintyGate


class RoutedGateError(ValueError):
    """The routed gate was asked to answer something it cannot account for."""


@dataclass
class RoutedAnswer:
    text: str
    model: str                      # cheap | strong | none
    verdict: str                    # gate verdict or "difficulty_direct"
    confidence: float
    escalated: bool
    abstained: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "verdict": self.verdict,
            "confidence": round(self.confidence, 4),
            "escalated": self.escalated,
            "abstained": self.abstained,
        }


class RoutedGate:
    """Uncertainty-gated candidate sampling over a cascade router."""

    def __init__(self, router: CascadeRouter, gate: UncertaintyGate,
                 *, samples: int = 3) -> None:
        if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
            raise ValueError("samples must be an integer >= 1")
        self.router = router
        self.gate = gate
        self.samples = samples
        self.queries = 0
        self.abstained = 0

    def answer(self, query: str, *, abstain_text: str = "I don't know.") -> RoutedAnswer:
        if not isinstance(query, str) or not query.strip():
            raise RoutedGateError("query is required")
        if not isinstance(abstain_text, str) or not abstain_text.strip():
            raise RoutedGateError("abstain text is required")
        self.queries += 1

        from .cascade import difficulty_estimate
        if difficulty_estimate(query) >= self.router.route_threshold:
            response = self._call(self.router.strong, query, self.router.strong_cost)
            self.router.decisions += 1
            self.router.strong_direct += 1
            if response is None:
                self.abstained += 1
                return self._abstain(abstain_text, "empty_strong")
            return RoutedAnswer(
                text=response.text,
                model="strong",
                verdict="difficulty_direct",
                confidence=response.confidence,
                escalated=False,
                abstained=False,
            )

        candidates = []
        for _ in range(self.samples):
            response = self._call(self.router.cheap, query, self.router.cheap_cost)
            if response is None:
                self.router.decisions += 1
                self.abstained += 1
                return self._abstain(abstain_text, "empty_sample")
            candidates.append(response)
        self.router.decisions += 1
        decision = self.gate.decide([
            Candidate(text=candidate.text, confidence=candidate.confidence) for candidate in candidates
        ])

        if decision.verdict is GateVerdict.ANSWER and decision.best is not None and decision.best.text.strip():
            return RoutedAnswer(
                text=decision.best.text,
                model="cheap",
                verdict=decision.reason,
                confidence=decision.best.confidence,
                escalated=False,
                abstained=False,
            )

        if decision.verdict is GateVerdict.ABSTAIN:
            self.abstained += 1
            return self._abstain(abstain_text, decision.reason)

        response = self._call(self.router.strong, query, self.router.strong_cost)
        self.router.escalations += 1
        if response is None:
            self.abstained += 1
            return self._abstain(abstain_text, "empty_escalation")
        return RoutedAnswer(
            text=response.text,
            model="strong",
            verdict="confidence_escalation",
            confidence=response.confidence,
            escalated=True,
            abstained=False,
        )

    def _call(self, model, query: str, cost: float):
        response = model(query)
        if not isinstance(response, ModelResponse) or not isinstance(response.text, str):
            raise RoutedGateError("model must return a text response")
        confidence = response.confidence
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            raise RoutedGateError("model confidence must be in [0, 1]")
        self.router.total_cost += cost
        if not response.text.strip():
            return None
        return response

    def _abstain(self, text: str, reason: str) -> RoutedAnswer:
        return RoutedAnswer(
            text=text,
            model="none",
            verdict=reason,
            confidence=0.0,
            escalated=False,
            abstained=True,
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "queries": self.queries,
            "abstained": self.abstained,
            "abstain_rate": round(self.abstained / max(1, self.queries), 4),
            "router": self.router.stats(),
            "gate": self.gate.stats(),
        }
