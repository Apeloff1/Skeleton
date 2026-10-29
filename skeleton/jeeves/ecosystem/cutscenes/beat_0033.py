"""Cutscene beat 0033.
"""
from __future__ import annotations

BEAT = "beat_0033"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (33 % 5) * 0.5, 2)
