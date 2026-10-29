"""Mass and clipped-G subsystem (4x).
Enforce mass <= prior * 1.1, multi-rule clips, G growth tracking.
"""
from __future__ import annotations
from typing import Any, Dict

class MassClipper:
    def __init__(self, prior_mass: float = 1.0):
        self.prior = prior_mass
        self.history = []
    def clip(self, proposed: float) -> float:
        limit = self.prior * 1.1
        clipped = min(proposed, limit)
        self.history.append(clipped)
        return clipped
    def check(self, current: float) -> bool:
        return current <= self.prior * 1.1
    def trajectory(self) -> Dict[str, Any]:
        return {"prior": self.prior, "last": self.history[-1] if self.history else self.prior, "steps": len(self.history)}

def clip_rule_0(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (0 % 5) * 0.01))

def clip_rule_1(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (1 % 5) * 0.01))

def apply_all(mass: float, prior: float) -> float:
    for i in range(2):
        mass = globals()[f"clip_rule_{i}"](mass, prior)
    return mass
