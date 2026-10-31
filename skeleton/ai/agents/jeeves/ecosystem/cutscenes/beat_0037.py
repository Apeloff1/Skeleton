"""Cutscene beat 0037.
"""
from __future__ import annotations

BEAT = "beat_0037"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (37 % 5) * 0.5, 2)
