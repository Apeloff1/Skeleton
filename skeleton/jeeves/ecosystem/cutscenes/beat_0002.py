"""Cutscene beat 0002.
"""
from __future__ import annotations

BEAT = "beat_0002"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (2 % 5) * 0.5, 2)
