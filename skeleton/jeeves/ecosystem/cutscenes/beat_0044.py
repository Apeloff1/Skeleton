"""Cutscene beat 0044.
"""
from __future__ import annotations

BEAT = "beat_0044"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (44 % 5) * 0.5, 2)
