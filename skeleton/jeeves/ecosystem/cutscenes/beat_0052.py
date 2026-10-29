"""Cutscene beat 0052.
"""
from __future__ import annotations

BEAT = "beat_0052"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (52 % 5) * 0.5, 2)
