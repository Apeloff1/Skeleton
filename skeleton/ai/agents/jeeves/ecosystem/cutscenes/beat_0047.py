"""Cutscene beat 0047.
"""
from __future__ import annotations

BEAT = "beat_0047"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (47 % 5) * 0.5, 2)
