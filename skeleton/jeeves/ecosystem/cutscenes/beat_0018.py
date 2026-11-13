"""Cutscene beat 0018.
"""
from __future__ import annotations

BEAT = "beat_0018"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (18 % 5) * 0.5, 2)
