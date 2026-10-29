"""Cutscene beat 0073.
"""
from __future__ import annotations

BEAT = "beat_0073"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (73 % 5) * 0.5, 2)
