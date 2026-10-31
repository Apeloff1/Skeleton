"""Cutscene beat 0000.
"""
from __future__ import annotations

BEAT = "beat_0000"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (0 % 5) * 0.5, 2)
