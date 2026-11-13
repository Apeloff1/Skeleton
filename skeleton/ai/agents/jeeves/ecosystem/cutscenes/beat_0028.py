"""Cutscene beat 0028.
"""
from __future__ import annotations

BEAT = "beat_0028"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (28 % 5) * 0.5, 2)
