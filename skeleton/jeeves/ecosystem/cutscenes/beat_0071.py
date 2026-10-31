"""Cutscene beat 0071.
"""
from __future__ import annotations

BEAT = "beat_0071"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (71 % 5) * 0.5, 2)
