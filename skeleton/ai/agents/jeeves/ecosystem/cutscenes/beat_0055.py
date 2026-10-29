"""Cutscene beat 0055.
"""
from __future__ import annotations

BEAT = "beat_0055"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (55 % 5) * 0.5, 2)
