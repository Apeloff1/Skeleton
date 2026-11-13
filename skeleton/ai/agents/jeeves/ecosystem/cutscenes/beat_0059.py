"""Cutscene beat 0059.
"""
from __future__ import annotations

BEAT = "beat_0059"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (59 % 5) * 0.5, 2)
