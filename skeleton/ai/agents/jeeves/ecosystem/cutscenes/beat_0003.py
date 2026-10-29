"""Cutscene beat 0003.
"""
from __future__ import annotations

BEAT = "beat_0003"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (3 % 5) * 0.5, 2)
