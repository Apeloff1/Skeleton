"""Cutscene beat 0062.
"""
from __future__ import annotations

BEAT = "beat_0062"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (62 % 5) * 0.5, 2)
