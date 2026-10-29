"""Cutscene beat 0074.
"""
from __future__ import annotations

BEAT = "beat_0074"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (74 % 5) * 0.5, 2)
