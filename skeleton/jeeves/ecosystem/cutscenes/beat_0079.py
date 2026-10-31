"""Cutscene beat 0079.
"""
from __future__ import annotations

BEAT = "beat_0079"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (79 % 5) * 0.5, 2)
