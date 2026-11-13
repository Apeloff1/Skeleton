"""Cutscene beat 0077.
"""
from __future__ import annotations

BEAT = "beat_0077"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (77 % 5) * 0.5, 2)
