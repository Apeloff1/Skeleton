"""Cutscene beat 0050.
"""
from __future__ import annotations

BEAT = "beat_0050"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (50 % 5) * 0.5, 2)
