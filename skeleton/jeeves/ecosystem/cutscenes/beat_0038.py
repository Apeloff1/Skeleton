"""Cutscene beat 0038.
"""
from __future__ import annotations

BEAT = "beat_0038"

def sequence() -> list[str]:
    return ["setup", "action", "resolve"]

def duration() -> float:
    return round(2.0 + (38 % 5) * 0.5, 2)
