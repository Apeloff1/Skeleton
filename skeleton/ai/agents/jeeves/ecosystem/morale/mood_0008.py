"""Morale track 0008.
"""
from __future__ import annotations

MOOD = "mood_0008"

def adjust(current: int, delta: int) -> int:
    return max(0, min(100, current + delta))

def state(value: int) -> str:
    if value >= 70:
        return "high"
    if value >= 40:
        return "steady"
    return "low"
