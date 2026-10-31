"""Cutscene beat 0001.
"""
from __future__ import annotations

BEAT = "beat_0001"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (1 % 5) * 0.5, 2)
