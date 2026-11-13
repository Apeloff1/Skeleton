"""Cutscene beat 0072.
"""
from __future__ import annotations

BEAT = "beat_0072"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (72 % 5) * 0.5, 2)
