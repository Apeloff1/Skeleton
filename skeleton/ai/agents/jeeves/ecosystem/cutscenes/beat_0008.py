"""Cutscene beat 0008.
"""
from __future__ import annotations

BEAT = "beat_0008"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (8 % 5) * 0.5, 2)
