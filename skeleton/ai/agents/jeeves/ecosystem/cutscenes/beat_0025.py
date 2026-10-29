"""Cutscene beat 0025.
"""
from __future__ import annotations

BEAT = "beat_0025"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (25 % 5) * 0.5, 2)
