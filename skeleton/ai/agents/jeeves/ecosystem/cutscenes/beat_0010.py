"""Cutscene beat 0010.
"""
from __future__ import annotations

BEAT = "beat_0010"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (10 % 5) * 0.5, 2)
