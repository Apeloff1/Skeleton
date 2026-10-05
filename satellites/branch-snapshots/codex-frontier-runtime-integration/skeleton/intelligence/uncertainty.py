"""Uncertainty gating — abstain when the model doesn't know.

Wave-4 SOTA (entropy-gated generation work): sampling N candidates and
answering only when the distribution is confident beats always answering.
This gate estimates uncertainty from a candidate set *without* needing the
model's logits — token-distribution entropy over the candidates' outputs
is a usable proxy: if the candidates diverge wildly, confidence is low and
the right answer is to abstain or escalate.

Two signals, combined:

1. **Self-confidence** — mean of each candidate's reported confidence.
2. **Agreement entropy** — Shannon entropy over candidate answers;
   high divergence ⇒ low agreement ⇒ uncertainty.

The gate's verdict is one of: ANSWER (confident), ABSTAIN (say you don't
know), or ESCALATE (hand to a stronger model — composes with the cascade
router). Pure domain; candidates are (text, confidence) pairs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


class GateVerdict(str, Enum):
    ANSWER = "answer"
    ABSTAIN = "abstain"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class Candidate:
    text: str
    confidence: float


@dataclass(frozen=True)
class GateDecision:
    verdict: GateVerdict
    best: Optional[Candidate]
    mean_confidence: float
    agreement: float                  # 0..1 — fraction sharing the modal answer
    entropy: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "best": None if self.best is None else {"text": self.best.text,
                                                    "confidence": self.best.confidence},
            "mean_confidence": round(self.mean_confidence, 4),
            "agreement": round(self.agreement, 4),
            "entropy": round(self.entropy, 4),
            "reason": self.reason,
        }


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().split())[:200]


class UncertaintyGate:
    """Decide whether to answer, abstain, or escalate from a candidate set."""

    def __init__(
        self,
        *,
        answer_threshold: float = 0.65,
        escalate_threshold: float = 0.40,
        min_agreement: float = 0.5,
    ) -> None:
        if not 0.0 < escalate_threshold < answer_threshold <= 1.0:
            raise ValueError("need 0 < escalate < answer <= 1")
        self.answer_threshold = answer_threshold
        self.escalate_threshold = escalate_threshold
        self.min_agreement = min_agreement
        self.decisions = 0
        self.abstentions = 0
        self.escalations = 0

    def decide(self, candidates: Sequence[Candidate]) -> GateDecision:
        self.decisions += 1
        if not candidates:
            self.abstentions += 1
            return GateDecision(
                verdict=GateVerdict.ABSTAIN, best=None,
                mean_confidence=0.0, agreement=0.0, entropy=0.0,
                reason="no_candidates",
            )

        mean_conf = sum(c.confidence for c in candidates) / len(candidates)

        # agreement: modal share of normalised answers
        counts: Dict[str, int] = {}
        for c in candidates:
            key = _normalise(c.text)
            counts[key] = counts.get(key, 0) + 1
        modal_share = max(counts.values()) / len(candidates)
        # entropy over answer distribution (nats, normalised by ln(n))
        n = len(candidates)
        entropy = 0.0
        for count in counts.values():
            p = count / n
            entropy -= p * math.log(p)
        norm_entropy = entropy / math.log(n) if n > 1 else 0.0

        # effective confidence: self-report discounted by disagreement
        effective = mean_conf * (0.5 + 0.5 * modal_share)
        best = max(candidates, key=lambda c: c.confidence)

        if effective >= self.answer_threshold and modal_share >= self.min_agreement:
            verdict = GateVerdict.ANSWER
            reason = "confident_agreement"
        elif effective < self.escalate_threshold:
            verdict = GateVerdict.ESCALATE
            reason = "below_escalate_threshold"
            self.escalations += 1
        else:
            verdict = GateVerdict.ABSTAIN
            reason = "uncertain_middle_band"
            self.abstentions += 1

        return GateDecision(
            verdict=verdict, best=best,
            mean_confidence=mean_conf, agreement=modal_share,
            entropy=norm_entropy, reason=reason,
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "decisions": self.decisions,
            "abstentions": self.abstentions,
            "escalations": self.escalations,
            "abstain_rate": round(self.abstentions / max(1, self.decisions), 4),
        }
