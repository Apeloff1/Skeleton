"""Cutscene beat 0045.
"""
from __future__ import annotations

BEAT = "beat_0045"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (45 % 5) * 0.5, 2)
