"""Cutscene beat 0056.
"""
from __future__ import annotations

BEAT = "beat_0056"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (56 % 5) * 0.5, 2)
