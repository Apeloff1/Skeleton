"""Cutscene beat 0011.
"""
from __future__ import annotations

BEAT = "beat_0011"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (11 % 5) * 0.5, 2)
