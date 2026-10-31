"""Cutscene beat 0040.
"""
from __future__ import annotations

BEAT = "beat_0040"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (40 % 5) * 0.5, 2)
