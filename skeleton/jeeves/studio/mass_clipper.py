"""Mass and clipped-G subsystem.
Enforce mass <= prior * 1.1, G growth only via MHC * S with clips.
"""
from __future__ import annotations
from typing import Any, Dict

class MassClipper:
    def __init__(self, prior_mass: float = 1.0):
        self.prior = prior_mass
    def clip(self, proposed: float) -> float:
        limit = self.prior * 1.1
        return min(proposed, limit)
    def check(self, current: float) -> bool:
        return current <= self.prior * 1.1

def clip_rule_0(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (0 % 5) * 0.01))

def clip_rule_1(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (1 % 5) * 0.01))

def clip_rule_2(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (2 % 5) * 0.01))

def clip_rule_3(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (3 % 5) * 0.01))

def clip_rule_4(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (4 % 5) * 0.01))

def clip_rule_5(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (5 % 5) * 0.01))

def clip_rule_6(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (6 % 5) * 0.01))

def clip_rule_7(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (7 % 5) * 0.01))

def clip_rule_8(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (8 % 5) * 0.01))

def clip_rule_9(mass: float, prior: float) -> float:
    return min(mass, prior * (1.05 + (9 % 5) * 0.01))

def apply_all(mass: float, prior: float) -> float:
    for i in range(10):
        mass = globals()[f"clip_rule_{i}"](mass, prior)
    return mass
