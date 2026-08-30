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
        if samples < 1:
            raise ValueError("samples must be >= 1")
        self.router = router
        self.gate = gate
        self.samples = samples
        self.queries = 0
        self.abstained = 0

    def answer(self, query: str, *, abstain_text: str = "I don't know.") -> RoutedAnswer:
        self.queries += 1

        # 1. hard queries: no sampling waste, straight to strong
        from .cascade import difficulty_estimate
        if difficulty_estimate(query) >= self.router.route_threshold:
            resp = self.router.strong(query)
            self.router.decisions += 1
            self.router.strong_direct += 1
            self.router.total_cost += self.router.strong_cost
            return RoutedAnswer(text=resp.text, model="strong",
                                verdict="difficulty_direct",
                                confidence=resp.confidence,
                                escalated=False, abstained=False)

        # 2. cheap candidates + gate
        self.router.decisions += 1
        self.router.total_cost += self.router.cheap_cost
        candidates = [self.router.cheap(query) for _ in range(self.samples)]
        decision = self.gate.decide([
            Candidate(text=c.text, confidence=c.confidence) for c in candidates
        ])

        if decision.verdict is GateVerdict.ANSWER and decision.best is not None:
            return RoutedAnswer(text=decision.best.text, model="cheap",
                                verdict=decision.reason,
                                confidence=decision.best.confidence,
                                escalated=False, abstained=False)

        if decision.verdict is GateVerdict.ABSTAIN:
            self.abstained += 1
            return RoutedAnswer(text=abstain_text, model="none",
                                verdict=decision.reason,
                                confidence=decision.mean_confidence,
                                escalated=False, abstained=True)

        # 3. ESCALATE → strong through the cascade's accounting
        self.router.escalations += 1
        self.router.total_cost += self.router.strong_cost
        resp = self.router.strong(query)
        return RoutedAnswer(text=resp.text, model="strong",
                            verdict="confidence_escalation",
                            confidence=resp.confidence,
                            escalated=True, abstained=False)

    def stats(self) -> Dict[str, Any]:
        return {
            "queries": self.queries,
            "abstained": self.abstained,
            "abstain_rate": round(self.abstained / max(1, self.queries), 4),
            "router": self.router.stats(),
            "gate": self.gate.stats(),
        }
