"""Cutscene beat 0063.
"""
from __future__ import annotations

BEAT = "beat_0063"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (63 % 5) * 0.5, 2)
