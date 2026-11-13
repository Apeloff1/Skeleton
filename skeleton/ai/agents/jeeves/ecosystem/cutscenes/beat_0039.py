"""Cutscene beat 0039.
"""
from __future__ import annotations

BEAT = "beat_0039"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (39 % 5) * 0.5, 2)
