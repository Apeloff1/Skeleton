"""Cutscene beat 0061.
"""
from __future__ import annotations

BEAT = "beat_0061"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (61 % 5) * 0.5, 2)
