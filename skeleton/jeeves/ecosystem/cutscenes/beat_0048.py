"""Cutscene beat 0048.
"""
from __future__ import annotations

BEAT = "beat_0048"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (48 % 5) * 0.5, 2)
