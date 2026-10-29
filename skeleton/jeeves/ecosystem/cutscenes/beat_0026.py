"""Cutscene beat 0026.
"""
from __future__ import annotations

BEAT = "beat_0026"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (26 % 5) * 0.5, 2)
