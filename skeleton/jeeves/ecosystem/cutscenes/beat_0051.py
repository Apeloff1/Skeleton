"""Cutscene beat 0051.
"""
from __future__ import annotations

BEAT = "beat_0051"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (51 % 5) * 0.5, 2)
