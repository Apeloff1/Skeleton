"""Cutscene beat 0027.
"""
from __future__ import annotations

BEAT = "beat_0027"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (27 % 5) * 0.5, 2)
