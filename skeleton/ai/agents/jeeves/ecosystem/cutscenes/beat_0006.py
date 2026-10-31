"""Cutscene beat 0006.
"""
from __future__ import annotations

BEAT = "beat_0006"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (6 % 5) * 0.5, 2)
