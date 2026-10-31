"""Cutscene beat 0049.
"""
from __future__ import annotations

BEAT = "beat_0049"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (49 % 5) * 0.5, 2)
