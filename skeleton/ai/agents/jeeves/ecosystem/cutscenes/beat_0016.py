"""Cutscene beat 0016.
"""
from __future__ import annotations

BEAT = "beat_0016"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (16 % 5) * 0.5, 2)
