"""Cutscene beat 0023.
"""
from __future__ import annotations

BEAT = "beat_0023"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (23 % 5) * 0.5, 2)
