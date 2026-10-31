"""Cutscene beat 0013.
"""
from __future__ import annotations

BEAT = "beat_0013"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (13 % 5) * 0.5, 2)
