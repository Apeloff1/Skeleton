"""
gameforge.jeeves.free_tier — layered FREE-tier multimodal cascade + budget.

Fronts the paid LLM with FREE tiers so cost is only incurred when the free
tiers are genuinely exhausted (the user's cost-cutting mandate):

  Tier 0  LOCAL      — deterministic extractive synthesis + local artifact
                       generation (PDF/chart/graph/sheet). Zero cost, unlimited.
  Tier 1  KNOWLEDGE  — free knowledge APIs (Wikipedia) already integrated;
                       counts against a generous free quota window.
  Tier 2  PAID       — Emergent LLM (Claude / gpt-4o). Only reached when a
                       request NEEDS generative reasoning AND the free budget
                       for this window is spent.

A rolling-window budget tracks free "units". ``decide(needs_reasoning)`` returns
the tier to use. Also tracks last-activity so the scheduler can detect >4h idle
and spend the whole free budget augmenting Jeeves + the jury/wiki queue.
"""
from __future__ import annotations

import time
from typing import Dict

# free-tier budget: generous free units per rolling window before we consider
# escalation "expensive". Local (tier 0) is always free and never consumes this.
_WINDOW_S = 3600.0          # 1-hour rolling window
_FREE_UNITS = 240           # free knowledge/paid-substitute units per window
IDLE_THRESHOLD_S = 4 * 3600  # 4 hours


class FreeTierRouter:
    def __init__(self):
        self.window_start = time.time()
        self.free_used = 0
        self.escalations = 0
        self.local_served = 0
        self.last_activity = time.time()
        self.idle_augmentations = 0

    def _roll(self):
        now = time.time()
        if now - self.window_start >= _WINDOW_S:
            self.window_start = now
            self.free_used = 0

    def touch(self):
        self.last_activity = time.time()

    def free_remaining(self) -> int:
        self._roll()
        return max(0, _FREE_UNITS - self.free_used)

    def decide(self, needs_reasoning: bool) -> str:
        """Return the tier to serve this request: 'local' | 'free' | 'paid'."""
        self.touch()
        self._roll()
        if not needs_reasoning:
            self.local_served += 1
            return "local"           # tier 0 — always free
        if self.free_remaining() > 0:
            self.free_used += 1
            return "free"            # tier 1 — free knowledge substitute
        self.escalations += 1
        return "paid"                # tier 2 — escalate to paid LLM

    def idle_seconds(self) -> float:
        return time.time() - self.last_activity

    def should_augment_idle(self) -> bool:
        return self.idle_seconds() >= IDLE_THRESHOLD_S

    def stats(self) -> Dict:
        self._roll()
        return {
            "window_seconds": _WINDOW_S,
            "free_units_per_window": _FREE_UNITS,
            "free_used": self.free_used,
            "free_remaining": self.free_remaining(),
            "local_served": self.local_served,
            "escalations_to_paid": self.escalations,
            "idle_seconds": round(self.idle_seconds(), 1),
            "idle_threshold_seconds": IDLE_THRESHOLD_S,
            "idle_augmentations": self.idle_augmentations,
        }


free_tier = FreeTierRouter()

__all__ = ["FreeTierRouter", "free_tier", "IDLE_THRESHOLD_S"]
