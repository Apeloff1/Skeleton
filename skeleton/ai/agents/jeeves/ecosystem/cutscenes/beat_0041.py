"""Cutscene beat 0041.
"""
from __future__ import annotations

BEAT = "beat_0041"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (41 % 5) * 0.5, 2)
