"""Cycle 0021.
"""
from __future__ import annotations

CYCLE = "cycle_0021"

def phase(t: float) -> str:
    t = t % 24.0
    if t < 6:
        return "night"
    if t < 12:
        return "morning"
    if t < 18:
        return "day"
    return "evening"
