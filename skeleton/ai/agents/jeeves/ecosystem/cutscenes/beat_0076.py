"""Cutscene beat 0076.
"""
from __future__ import annotations

BEAT = "beat_0076"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (76 % 5) * 0.5, 2)
