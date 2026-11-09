"""Cutscene beat 0031.
"""
from __future__ import annotations

BEAT = "beat_0031"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (31 % 5) * 0.5, 2)
