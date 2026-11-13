"""Cutscene beat 0060.
"""
from __future__ import annotations

BEAT = "beat_0060"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (60 % 5) * 0.5, 2)
