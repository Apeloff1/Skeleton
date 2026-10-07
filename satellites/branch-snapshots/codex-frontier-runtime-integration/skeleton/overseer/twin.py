"""
Skeleton Overseer — Digital Twin + Meta-Cognition

The two layers above control: a live simulation of the organism
running in shadow, and a meta-cognitive evaluator scoring the
engine's own control quality — rewriting its own parameters when
it detects systematic miscalibration.

Digital Twin:
- Maintains a shadow copy of the system state driven by the same
  inputs the real system receives (throttle, demand, regime).
- Simulates counterfactuals: "what if we had throttled 20% harder
  ten ticks ago?" — answered by replaying history through the
  identified channel models along an alternate control path.
- Counterfactual scores feed the meta-cognition layer: the engine
  learns whether its actual decisions beat the alternatives.

Meta-Cognition:
- Control-quality scorecard per channel: tracking error, overshoot,
  oscillation index (sign changes in error), settling time.
- Regret: actual cost minus best counterfactual cost, accumulated
  over a rolling window. Persistent regret → parameter rewrite.
- Self-rewrite rules (bounded, auditable): adjust PID gains ±25%,
  shift setpoints within safety envelopes, widen/narrow MPC horizon
  ±2. Every rewrite is logged with before/after and a reason —
  the engine can always explain its own mutation.
- Confidence: meta-cognition emits a trust score per decision;
  low-trust decisions fall back to conservative (V1-style) control.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.overseer.mpc import ChannelModel


# ---------------------------------------------------------------------------
# Digital Twin
# ---------------------------------------------------------------------------

@dataclass
class TwinState:
    """Shadow state of one simulation branch."""
    states: Dict[str, float]
    tick: int
    cumulative_cost: float = 0.0


@dataclass
class Counterfactual:
    """Result of replaying history along an alternate control path."""
    branch: str
    alternate_u: float
    simulated_ticks: int
    final_cost: float
    actual_cost: float
    delta: float  # final - actual (negative = alternative was better)

    def to_dict(self) -> Dict[str, Any]:
        return {"branch": self.branch, "alternate_u": round(self.alternate_u, 3),
                "ticks": self.simulated_ticks, "delta": round(self.delta, 4)}


class DigitalTwin:
    """Shadow simulation of the organism for counterfactual replay."""

    HISTORY = 32

    def __init__(self):
        self._history: List[Dict[str, Any]] = []
        self._stats = {"branches_run": 0}

    def record(self, states: Dict[str, float], u: float, demand: float, cost: float) -> None:
        self._history.append({"states": dict(states), "u": u, "demand": demand, "cost": cost})
        if len(self._history) > self.HISTORY:
            self._history.pop(0)

    def replay(self, models: Dict[str, ChannelModel],
               alternate_u: float, back_ticks: int = 10,
               setpoints: Optional[Dict[str, float]] = None) -> Counterfactual:
        """Replay the last N ticks with a constant alternate throttle."""
        self._stats["branches_run"] += 1
        window = self._history[-back_ticks:]
        if not window:
            return Counterfactual("empty", alternate_u, 0, 0.0, 0.0, 0.0)

        sim = dict(window[0]["states"])
        total_cost = 0.0
        actual_cost = sum(h["cost"] for h in window)

        for h in window:
            demand = h["demand"]
            for ch, model in models.items():
                x = sim.get(ch, 0.0)
                sp = (setpoints or {}).get(ch, x)
                total_cost += (x - sp) ** 2
                sim[ch] = model.predict(x, alternate_u, demand)

        return Counterfactual(
            branch=f"u={alternate_u:.2f}",
            alternate_u=alternate_u,
            simulated_ticks=len(window),
            final_cost=total_cost,
            actual_cost=actual_cost,
            delta=total_cost - actual_cost,
        )

    def grid_search(self, models: Dict[str, ChannelModel],
                    back_ticks: int = 10,
                    setpoints: Optional[Dict[str, float]] = None,
                    grid: Tuple[float, ...] = (0.3, 0.5, 0.7, 0.9, 1.0)) -> List[Counterfactual]:
        """Evaluate a grid of alternate constant throttles over history."""
        return [self.replay(models, u, back_ticks, setpoints) for u in grid]

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "history": len(self._history)}


# ---------------------------------------------------------------------------
# Meta-Cognition
# ---------------------------------------------------------------------------

@dataclass
class ChannelScorecard:
    """Control-quality metrics for one channel over the window."""
    channel: str
    mean_abs_error: float
    overshoot: float
    oscillation_index: float
    settling_ticks: int
    grade: str  # A | B | C | D

    def to_dict(self) -> Dict[str, Any]:
        return {"channel": self.channel, "mae": round(self.mean_abs_error, 4),
                "overshoot": round(self.overshoot, 4),
                "oscillation": round(self.oscillation_index, 3),
                "settling": self.settling_ticks, "grade": self.grade}


@dataclass
class ParameterRewrite:
    """One auditable self-mutation of the engine."""
    parameter: str
    before: Any
    after: Any
    reason: str
    at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {"parameter": self.parameter, "before": self.before,
                "after": self.after, "reason": self.reason}


class MetaCognition:
    """The engine evaluating and rewriting itself, bounded and auditable."""

    WINDOW = 32
    REGRET_THRESHOLD = 0.5
    MAX_REWRITE_DELTA = 0.25  # ±25% per rewrite

    def __init__(self):
        self._errors: Dict[str, List[float]] = {}
        self._regret_window: List[float] = []
        self.rewrites: List[ParameterRewrite] = []
        self._stats = {"scorecards": 0, "rewrites": 0, "low_trust_decisions": 0}

    # --- Scorecards ----------------------------------------------------------

    def observe_error(self, channel: str, error: float) -> None:
        errs = self._errors.setdefault(channel, [])
        errs.append(error)
        if len(errs) > self.WINDOW:
            errs.pop(0)

    def scorecard(self, channel: str) -> Optional[ChannelScorecard]:
        errs = self._errors.get(channel, [])
        if len(errs) < 4:
            return None
        mae = sum(abs(e) for e in errs) / len(errs)
        overshoot = max((-e for e in errs), default=0.0)
        sign_changes = sum(1 for i in range(1, len(errs))
                           if (errs[i] > 0) != (errs[i - 1] > 0))
        oscillation = sign_changes / (len(errs) - 1)
        settling = 0
        for e in reversed(errs):
            if abs(e) > 0.05:
                settling += 1
            else:
                break
        grade = ("A" if mae < 0.03 and oscillation < 0.2 else
                 "B" if mae < 0.07 and oscillation < 0.4 else
                 "C" if mae < 0.15 else "D")
        self._stats["scorecards"] += 1
        return ChannelScorecard(channel, mae, overshoot, oscillation, settling, grade)

    def all_scorecards(self) -> List[ChannelScorecard]:
        return [sc for ch in self._errors if (sc := self.scorecard(ch)) is not None]

    # --- Regret + trust --------------------------------------------------------

    def observe_regret(self, delta: float) -> None:
        """delta = actual - best counterfactual (positive = we did worse)."""
        self._regret_window.append(max(0.0, delta))
        if len(self._regret_window) > self.WINDOW:
            self._regret_window.pop(0)

    def mean_regret(self) -> float:
        return sum(self._regret_window) / max(1, len(self._regret_window))

    def trust(self) -> float:
        """Confidence in the engine's own control quality 0..1."""
        regret = self.mean_regret()
        cards = self.all_scorecards()
        if not cards:
            return 0.8  # insufficient data: cautiously high
        grade_score = {"A": 1.0, "B": 0.8, "C": 0.55, "D": 0.3}
        mean_grade = sum(grade_score[c.grade] for c in cards) / len(cards)
        trust = 0.6 * mean_grade + 0.4 * max(0.0, 1.0 - regret * 2.0)
        if trust < 0.4:
            self._stats["low_trust_decisions"] += 1
        return round(trust, 3)

    # --- Self-rewrite -------------------------------------------------------------

    def consider_rewrite(self, parameter: str, current: float,
                         proposed: float, reason: str) -> Optional[ParameterRewrite]:
        """Rewrite a parameter if regret is persistent; bounded ±25%."""
        if self.mean_regret() < self.REGRET_THRESHOLD:
            return None
        if current == 0:
            return None
        delta = (proposed - current) / abs(current)
        delta = max(-self.MAX_REWRITE_DELTA, min(self.MAX_REWRITE_DELTA, delta))
        new_value = current * (1.0 + delta)
        rewrite = ParameterRewrite(parameter, round(current, 4), round(new_value, 4), reason)
        self.rewrites.append(rewrite)
        self._stats["rewrites"] += 1
        # Reset regret window after mutation so its effect is measurable
        self._regret_window.clear()
        return rewrite

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "mean_regret": round(self.mean_regret(), 4),
            "trust": self.trust(),
            "scorecards": [c.to_dict() for c in self.all_scorecards()],
            "recent_rewrites": [r.to_dict() for r in self.rewrites[-5:]],
        }
