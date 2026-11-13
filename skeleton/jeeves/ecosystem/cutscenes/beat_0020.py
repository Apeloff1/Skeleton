"""Cutscene beat 0020.
"""
from __future__ import annotations

BEAT = "beat_0020"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (20 % 5) * 0.5, 2)
