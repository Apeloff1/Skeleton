"""Cutscene beat 0017.
"""
from __future__ import annotations

BEAT = "beat_0017"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (17 % 5) * 0.5, 2)
