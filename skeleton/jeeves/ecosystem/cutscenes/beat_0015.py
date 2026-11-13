"""Cutscene beat 0015.
"""
from __future__ import annotations

BEAT = "beat_0015"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (15 % 5) * 0.5, 2)
