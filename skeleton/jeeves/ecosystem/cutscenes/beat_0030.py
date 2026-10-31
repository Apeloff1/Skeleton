"""Cutscene beat 0030.
"""
from __future__ import annotations

BEAT = "beat_0030"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (30 % 5) * 0.5, 2)
