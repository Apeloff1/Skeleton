"""Cutscene beat 0069.
"""
from __future__ import annotations

BEAT = "beat_0069"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (69 % 5) * 0.5, 2)
