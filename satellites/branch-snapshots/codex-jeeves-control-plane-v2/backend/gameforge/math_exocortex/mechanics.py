from __future__ import annotations
"""
Virtual weights, counterweights, scales — exact mechanical equilibrium tools.
Uses Rational arithmetic via fractions module (certainty, no float drift).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple
import uuid


def _F(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    return Fraction(str(x)).limit_denominator(10**9)


@dataclass
class Weight:
    weight_id: str
    label: str
    mass: str  # Fraction as string for JSON stability
    arm: str = "0"  # lever arm distance
    side: str = "left"  # left | right

    @property
    def mass_f(self) -> Fraction:
        return _F(self.mass)

    @property
    def arm_f(self) -> Fraction:
        return _F(self.arm)

    def moment(self) -> Fraction:
        sign = Fraction(1) if self.side == "left" else Fraction(-1)
        return sign * self.mass_f * self.arm_f

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScaleState:
    scale_id: str
    fulcrum: str = "0"
    weights: List[Dict[str, Any]] = field(default_factory=list)
    balanced: bool = False
    net_moment: str = "0"
    left_moment: str = "0"
    right_moment: str = "0"
    message: str = ""


class VirtualScale:
    """
    Lever scale: equilibrium when Σ m_i * d_i (signed) = 0 exactly.
    """

    def __init__(self, scale_id: Optional[str] = None, fulcrum: Any = 0):
        self.scale_id = scale_id or str(uuid.uuid4())[:10]
        self.fulcrum = _F(fulcrum)
        self.weights: List[Weight] = []
        self.logs: List[Dict[str, Any]] = []

    def _log(self, event: str, **kw):
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": event, **kw})

    def add_weight(self, label: str, mass: Any, arm: Any, side: str = "left") -> Weight:
        if side not in ("left", "right"):
            raise ValueError("side must be left|right")
        w = Weight(
            weight_id=str(uuid.uuid4())[:8],
            label=label,
            mass=str(_F(mass)),
            arm=str(_F(arm)),
            side=side,
        )
        self.weights.append(w)
        self._log("add_weight", label=label, mass=w.mass, arm=w.arm, side=side)
        return w

    def add_counterweight(self, label: str, mass: Any, arm: Any) -> Weight:
        """Counterweight always on the right side by convention."""
        return self.add_weight(label, mass, arm, side="right")

    def net_moment(self) -> Fraction:
        total = Fraction(0)
        for w in self.weights:
            total += w.moment()
        return total

    def evaluate(self) -> ScaleState:
        left = Fraction(0)
        right = Fraction(0)
        for w in self.weights:
            m = w.mass_f * w.arm_f
            if w.side == "left":
                left += m
            else:
                right += m
        net = left - right
        balanced = net == 0
        msg = "balanced (exact)" if balanced else f"imbalance net_moment={net}"
        state = ScaleState(
            scale_id=self.scale_id,
            fulcrum=str(self.fulcrum),
            weights=[w.to_dict() for w in self.weights],
            balanced=balanced,
            net_moment=str(net),
            left_moment=str(left),
            right_moment=str(right),
            message=msg,
        )
        self._log("evaluate", balanced=balanced, net=str(net))
        return state

    def required_counterweight(self, arm: Any) -> Dict[str, Any]:
        """Exact mass needed on the right at given arm to balance current left."""
        arm_f = _F(arm)
        if arm_f == 0:
            return {"ok": False, "error": "arm_must_be_nonzero"}
        left = sum((w.mass_f * w.arm_f for w in self.weights if w.side == "left"), Fraction(0))
        right_existing = sum((w.mass_f * w.arm_f for w in self.weights if w.side == "right"), Fraction(0))
        need = (left - right_existing) / arm_f
        self._log("required_counterweight", arm=str(arm_f), mass=str(need))
        return {
            "ok": True,
            "arm": str(arm_f),
            "required_mass": str(need),
            "required_mass_float_display_only": float(need),
            "certainty": "exact_rational",
        }


class MechanicalToolkit:
    """Advanced deterministic mechanics helpers."""

    def __init__(self):
        self.scales: Dict[str, VirtualScale] = {}
        self.logs: List[Dict[str, Any]] = []

    def _log(self, event: str, **kw):
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": event, **kw})

    def create_scale(self) -> VirtualScale:
        s = VirtualScale()
        self.scales[s.scale_id] = s
        self._log("create_scale", id=s.scale_id)
        return s

    def gear_ratio(self, teeth_a: int, teeth_b: int) -> Dict[str, Any]:
        if teeth_a <= 0 or teeth_b <= 0:
            return {"ok": False, "error": "teeth must be positive"}
        r = Fraction(teeth_a, teeth_b)
        self._log("gear_ratio", a=teeth_a, b=teeth_b, ratio=str(r))
        return {"ok": True, "ratio": str(r), "ratio_a_to_b": str(r), "certainty": "exact"}

    def pulley_advantage(self, supporting_strands: int) -> Dict[str, Any]:
        if supporting_strands <= 0:
            return {"ok": False, "error": "strands must be positive"}
        # ideal mechanical advantage = number of supporting strands
        self._log("pulley_advantage", strands=supporting_strands)
        return {
            "ok": True,
            "mechanical_advantage": str(Fraction(supporting_strands, 1)),
            "certainty": "exact_ideal_model",
        }

    def balance_equation(self, masses_arms: List[Tuple[Any, Any]]) -> Dict[str, Any]:
        """Σ m_i * d_i with signed arms (negative = opposite side). Exact."""
        total = Fraction(0)
        terms = []
        for m, d in masses_arms:
            term = _F(m) * _F(d)
            terms.append(str(term))
            total += term
        self._log("balance_equation", terms=terms, total=str(total))
        return {
            "ok": True,
            "terms": terms,
            "sum": str(total),
            "balanced": total == 0,
            "certainty": "exact_rational",
        }
