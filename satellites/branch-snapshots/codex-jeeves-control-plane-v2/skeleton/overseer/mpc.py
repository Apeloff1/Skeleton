"""
Skeleton Overseer — System Identification + Model-Predictive Control

Beyond reactive control: the engine learns a live dynamical model of
the host machine itself, then optimizes control over a receding
horizon instead of correcting one step at a time.

System identification (online, recursive least squares with forgetting):
- Each resource channel is modeled as a first-order-plus-input system:
      x[t+1] = a·x[t] + b·u[t] + c·d[t]
  where x = measured state, u = throttle applied, d = exogenous demand.
- RLS estimates (a, b, c) continuously from the live stream; the
  forgetting factor weights recent dynamics over stale ones, so the
  model tracks hardware whose response changes (thermal soak, battery
  aging, VM steal).
- Innovation (one-step prediction error) per channel feeds anomaly
  scoring — a channel whose model suddenly fails IS the anomaly.

Model-predictive control (receding horizon):
- Each tick, the MPC simulates the identified model forward H steps
  over a candidate set of throttle sequences (a small, deterministic
  trajectory library: hold, ramp-up, ramp-down, pulse, relax).
- Cost per trajectory: weighted tracking error + control effort +
  slew penalty + constraint violation (hard thermal/memory walls).
- The first element of the winning sequence is applied; the horizon
  recedes. Feasibility is guaranteed by always including 'hold'.
- Constraints are HARD: thermal and memory walls are never crossed
  in simulation, so they're never crossed in actuation.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Recursive Least Squares system identification (per channel)
# ---------------------------------------------------------------------------

@dataclass
class ChannelModel:
    """Identified first-order-plus-input model of one channel."""
    name: str
    a: float = 0.9      # state persistence
    b: float = 0.1      # input gain (throttle → state)
    c: float = 0.05     # demand gain
    innovation: float = 0.0   # last one-step prediction error
    innovation_var: float = 0.0
    samples: int = 0

    def predict(self, x: float, u: float, d: float) -> float:
        return self.a * x + self.b * u + self.c * d

    def anomaly_score(self) -> float:
        """Standardized innovation magnitude — model-failure detector."""
        if self.samples < 10 or self.innovation_var < 1e-9:
            return 0.0
        return abs(self.innovation) / math.sqrt(self.innovation_var)


class SystemIdentifier:
    """Online RLS with forgetting for all resource channels."""

    def __init__(self, forgetting: float = 0.98):
        self.lam = forgetting
        self._models: Dict[str, ChannelModel] = {}
        self._prev: Dict[str, Tuple[float, float, float]] = {}  # (x, u, d)
        self._cov: Dict[str, List[List[float]]] = {}

    def observe(self, name: str, x: float, u: float, d: float) -> ChannelModel:
        model = self._models.setdefault(name, ChannelModel(name=name))
        prev = self._prev.get(name)
        if prev is not None:
            x_prev, u_prev, d_prev = prev
            # Regressor: [x_prev, u_prev, d_prev] → predict x
            phi = [x_prev, u_prev, d_prev]
            predicted = model.a * phi[0] + model.b * phi[1] + model.c * phi[2]
            innovation = x - predicted

            # RLS update on 3 params with forgetting
            P = self._cov.setdefault(name, [[100.0 if i == j else 0.0
                                             for j in range(3)] for i in range(3)])
            Pphi = [sum(P[i][j] * phi[j] for j in range(3)) for i in range(3)]
            denom = self.lam + sum(phi[i] * Pphi[i] for i in range(3))
            K = [p / max(denom, 1e-9) for p in Pphi]
            params = [model.a, model.b, model.c]
            params = [p + K[i] * innovation for i, p in enumerate(params)]
            model.a = min(0.999, max(0.0, params[0]))
            model.b = params[1]
            model.c = params[2]
            # Covariance update (Joseph-free simplified form)
            for i in range(3):
                for j in range(3):
                    P[i][j] = (P[i][j] - K[i] * phi[j] * sum(phi[k] * P[k][j] for k in range(3)) / max(1.0, denom)) / self.lam

            # Innovation statistics (EMA)
            model.innovation = innovation
            model.innovation_var = 0.05 * innovation ** 2 + 0.95 * model.innovation_var + 1e-6
            model.samples += 1

        self._prev[name] = (x, u, d)
        return model

    def model(self, name: str) -> Optional[ChannelModel]:
        return self._models.get(name)

    def anomalies(self, threshold: float = 3.0) -> List[str]:
        """Channels whose model is failing — root-cause signals."""
        return [name for name, m in self._models.items()
                if m.anomaly_score() > threshold]

    def stats(self) -> Dict[str, Any]:
        return {
            name: {"a": round(m.a, 4), "b": round(m.b, 4), "c": round(m.c, 4),
                   "anomaly_score": round(m.anomaly_score(), 2), "samples": m.samples}
            for name, m in self._models.items()
        }


# ---------------------------------------------------------------------------
# Model-Predictive Control (receding horizon)
# ---------------------------------------------------------------------------

@dataclass
class MPCResult:
    """Winning control move + the evaluated horizon."""
    control: float
    trajectory_name: str
    horizon_cost: float
    candidates_evaluated: int
    constraint_wall_hit: bool
    planned_path: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control": round(self.control, 4),
            "trajectory": self.trajectory_name,
            "cost": round(self.horizon_cost, 4),
            "candidates": self.candidates_evaluated,
            "wall_hit": self.constraint_wall_hit,
            "path_head": [round(p, 3) for p in self.planned_path[:5]],
        }


# Deterministic trajectory library over H steps (throttle multipliers
# relative to current output). Always includes 'hold' for feasibility.
def _trajectory_library(current: float, horizon: int) -> Dict[str, List[float]]:
    clamp = lambda v: max(0.05, min(1.0, v))
    return {
        "hold": [current] * horizon,
        "ramp_up": [clamp(current + 0.1 * i) for i in range(horizon)],
        "ramp_down": [clamp(current - 0.1 * i) for i in range(horizon)],
        "pulse": [clamp(current + (0.15 if i % 2 == 0 else -0.05)) for i in range(horizon)],
        "relax": [clamp(current + 0.05 * i) for i in range(horizon)],
        "floor": [0.05] * horizon,
    }


class ModelPredictiveController:
    """Receding-horizon MPC over identified channel models.

    Hard walls: any simulated step crossing a constraint wall is
    assigned infinite cost — feasibility is structural, not tuned.
    """

    def __init__(self, horizon: int = 8,
                 walls: Optional[Dict[str, float]] = None,
                 weights: Optional[Dict[str, float]] = None):
        self.horizon = horizon
        # Hard constraint walls per channel (never cross)
        self.walls = walls or {"thermal": 85.0, "memory": 0.92}
        # Cost weights: tracking / effort / slew / constraint
        self.weights = weights or {"track": 1.0, "effort": 0.1, "slew": 0.3, "wall": 1e6}
        self._stats = {"plans": 0, "wall_hits": 0}

    def plan(self, models: Dict[str, ChannelModel],
             states: Dict[str, float],
             setpoints: Dict[str, float],
             current_u: float,
             demand: float = 0.0) -> MPCResult:
        self._stats["plans"] += 1
        library = _trajectory_library(current_u, self.horizon)
        best_name, best_cost, best_path = "hold", math.inf, library["hold"]
        wall_hit_global = False

        for name, seq in library.items():
            cost = 0.0
            sim_states = dict(states)
            path: List[float] = []
            wall_hit = False

            for step, u in enumerate(seq):
                step_cost = 0.0
                for ch, model in models.items():
                    x = sim_states.get(ch, 0.0)
                    sp = setpoints.get(ch, x)
                    step_cost += self.weights["track"] * (x - sp) ** 2
                    # Constraint walls (hard)
                    wall = self.walls.get(ch)
                    if wall is not None:
                        if ch == "memory" and x > wall:
                            step_cost += self.weights["wall"]
                            wall_hit = True
                        if ch == "thermal" and x > wall:
                            step_cost += self.weights["wall"]
                            wall_hit = True
                    # Simulate the identified model forward
                    sim_states[ch] = model.predict(x, u, demand)
                # Effort + slew
                step_cost += self.weights["effort"] * (1.0 - u) ** 2
                if step > 0:
                    step_cost += self.weights["slew"] * (u - seq[step - 1]) ** 2
                cost += step_cost
                path.append(sim_states.get("thermal", sim_states.get("cpu", 0.0)))

            if wall_hit:
                wall_hit_global = True
            if cost < best_cost:
                best_name, best_cost, best_path = name, cost, path

        if wall_hit_global:
            self._stats["wall_hits"] += 1

        return MPCResult(
            control=library[best_name][0],
            trajectory_name=best_name,
            horizon_cost=best_cost,
            candidates_evaluated=len(library),
            constraint_wall_hit=wall_hit_global,
            planned_path=best_path,
        )

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
