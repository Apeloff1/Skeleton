"""Bounded self-verification — verify a step, but know when to stop.

Wave-2 SOTA (2026 work on the self-verification dilemma): reflective loops
improve answers up to a point, then *suppress* good ones — experience-heavy
agents learn to stop early, not to reflect forever. This module gives the
loop a principled stop condition:

  stop when  marginal_gain = conf_n - conf_{n-1}  falls below ``min_gain``
  or when ``max_rounds`` is reached, whichever comes first.

Wave-4 extension (test-time-compute budget forcing, 2026-08-30):
``min_rounds`` forces the loop to keep verifying even when the marginal
gain says stop — the "Wait, think more" direction of budget control.
Early-stop rules only apply once ``min_rounds`` rounds have run.

A "verifier" is any callable ``(claim, context) -> VerificationVerdict``;
the loop is agnostic about what verification means (unit check, rubric
score, critique-and-revise). It composes with the existing pipeline layer
but stays pure domain — no model required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class VerificationVerdict:
    """One round of verification over a claim."""
    confidence: float                 # 0..1 — verifier's confidence in the claim
    issues: Tuple[str, ...] = ()      # named problems, if any
    revised: Optional[str] = None     # improved claim, if the verifier revises


@dataclass
class VerificationTrace:
    """Full record of one bounded verification session."""
    rounds: int = 0
    history: List[float] = field(default_factory=list)
    final_claim: str = ""
    stopped_reason: str = "max_rounds"
    forced_rounds: int = 0            # rounds that ran only because of min_rounds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rounds": self.rounds,
            "history": list(self.history),
            "final_claim": self.final_claim,
            "stopped_reason": self.stopped_reason,
            "forced_rounds": self.forced_rounds,
        }


VerifierFn = Callable[[str, Optional[Dict[str, Any]]], VerificationVerdict]


class VerificationLoop:
    """Bounded critique-and-revise loop with marginal-gain stop + budget forcing."""

    def __init__(self, *, max_rounds: int = 3, min_gain: float = 0.05,
                 accept_threshold: float = 0.9, min_rounds: int = 1) -> None:
        if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
            raise ValueError("max_rounds must be an integer >= 1")
        if isinstance(min_rounds, bool) or not isinstance(min_rounds, int) or not 1 <= min_rounds <= max_rounds:
            raise ValueError("min_rounds must be an integer within [1, max_rounds]")
        if isinstance(min_gain, bool) or not isinstance(min_gain, (int, float)) or min_gain < 0 or min_gain != min_gain or min_gain == float("inf"):
            raise ValueError("min_gain must be a finite number >= 0")
        if isinstance(accept_threshold, bool) or not isinstance(accept_threshold, (int, float)) or not 0 < float(accept_threshold) <= 1:
            raise ValueError("accept_threshold must be in (0, 1]")
        self.max_rounds = max_rounds
        self.min_gain = float(min_gain)
        self.accept_threshold = float(accept_threshold)
        self.min_rounds = min_rounds
        self.sessions = 0

    def run(
        self,
        claim: str,
        verifier: VerifierFn,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, VerificationTrace]:
        """Verify → revise → repeat, until gains flatten or quality suffices."""
        if not isinstance(claim, str) or not claim.strip():
            raise ValueError("claim is required")
        trace = VerificationTrace(final_claim=claim)
        current = claim
        prev_conf = 0.0
        for _ in range(self.max_rounds):
            verdict = verifier(current, context)
            trace.rounds += 1
            confidence = verdict.confidence
            usable = (
                not isinstance(confidence, bool)
                and isinstance(confidence, (int, float))
                and 0.0 <= float(confidence) <= 1.0
            )
            recorded = float(confidence) if usable else 0.0
            trace.history.append(round(recorded, 4))
            revised = verdict.revised
            pending_revision = revised is not None
            if isinstance(revised, str) and revised.strip():
                current = revised
            trace.final_claim = current
            issues = verdict.issues or ()
            if usable and recorded >= self.accept_threshold and not pending_revision and not issues:
                trace.stopped_reason = "accepted"
                break
            gain = recorded - prev_conf
            prev_conf = recorded
            if trace.rounds > 1 and gain < self.min_gain:
                if trace.rounds < self.min_rounds:
                    trace.forced_rounds += 1
                    continue
                trace.stopped_reason = "marginal_gain"
                break
        else:
            trace.stopped_reason = "max_rounds"
        self.sessions += 1
        return current, trace
