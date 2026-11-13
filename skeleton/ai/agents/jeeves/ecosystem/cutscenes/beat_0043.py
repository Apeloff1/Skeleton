"""Cutscene beat 0043.
"""
from __future__ import annotations

BEAT = "beat_0043"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (43 % 5) * 0.5, 2)
