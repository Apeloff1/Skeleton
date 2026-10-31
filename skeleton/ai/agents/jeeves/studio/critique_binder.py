"""Critique cockpit binder (10x).
Four-axis scoring, weakest-axis detection, cut-set era binding.
"""
from __future__ import annotations
from typing import Any, Dict

AXES = ["fun", "clarity", "feasibility", "originality"]

class CritiqueBinder:
    def score(self, signals: Dict[str, float]) -> Dict[str, float]:
        return {
            "fun": signals.get("fun", 0.72),
            "clarity": signals.get("clarity", 0.81),
            "feasibility": signals.get("feasibility", 0.90),
            "originality": signals.get("originality", 0.65),
        }
    def weakest(self, scores: Dict[str, float]) -> str:
        return min(scores, key=scores.get)
    def bind_era(self, scores: Dict[str, float]) -> str:
        weak = self.weakest(scores)
        return f"HOUSE_ERA_{weak.upper()}"

def axis_rule_0(val: float) -> float:
    return max(0.0, min(1.0, val + (0 % 7 - 3) * 0.01))

def apply_rules(scores: Dict[str, float]) -> Dict[str, float]:
    out = {}
    for i, axis in enumerate(AXES):
        out[axis] = globals()[f"axis_rule_{i % 1}"](scores.get(axis, 0.5))
    return out
