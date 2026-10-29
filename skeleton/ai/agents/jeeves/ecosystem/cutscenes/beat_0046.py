"""Cutscene beat 0046.
"""
from __future__ import annotations

BEAT = "beat_0046"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (46 % 5) * 0.5, 2)
