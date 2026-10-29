"""Cutscene beat 0029.
"""
from __future__ import annotations

BEAT = "beat_0029"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (29 % 5) * 0.5, 2)
