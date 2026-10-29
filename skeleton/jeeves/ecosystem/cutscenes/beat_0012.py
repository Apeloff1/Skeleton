"""Cutscene beat 0012.
"""
from __future__ import annotations

BEAT = "beat_0012"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (12 % 5) * 0.5, 2)
