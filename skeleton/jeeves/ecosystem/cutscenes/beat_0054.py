"""Cutscene beat 0054.
"""
from __future__ import annotations

BEAT = "beat_0054"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (54 % 5) * 0.5, 2)
