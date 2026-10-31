"""Cutscene beat 0007.
"""
from __future__ import annotations

BEAT = "beat_0007"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (7 % 5) * 0.5, 2)
