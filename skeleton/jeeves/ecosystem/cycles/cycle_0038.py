"""Cycle 0038.
"""
from __future__ import annotations

CYCLE = "cycle_0038"

def phase(t: float) -> str:
    t = t % 24.0
    if t < 6:
        return "night"
    if t < 12:
        return "morning"
    if t < 18:
        return "day"
    return "evening"
