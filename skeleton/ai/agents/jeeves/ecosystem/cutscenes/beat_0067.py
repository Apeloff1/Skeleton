"""Cutscene beat 0067.
"""
from __future__ import annotations

BEAT = "beat_0067"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (67 % 5) * 0.5, 2)
