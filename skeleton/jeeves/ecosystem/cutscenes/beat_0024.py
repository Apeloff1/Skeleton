"""Cutscene beat 0024.
"""
from __future__ import annotations

BEAT = "beat_0024"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (24 % 5) * 0.5, 2)
