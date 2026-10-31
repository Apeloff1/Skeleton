"""Cutscene beat 0009.
"""
from __future__ import annotations

BEAT = "beat_0009"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (9 % 5) * 0.5, 2)
