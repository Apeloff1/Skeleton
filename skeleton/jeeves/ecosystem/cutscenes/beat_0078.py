"""Cutscene beat 0078.
"""
from __future__ import annotations

BEAT = "beat_0078"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (78 % 5) * 0.5, 2)
