"""Cutscene beat 0021.
"""
from __future__ import annotations

BEAT = "beat_0021"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (21 % 5) * 0.5, 2)
