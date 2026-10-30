"""Morale track 0018.
"""
from __future__ import annotations

MOOD = "mood_0018"

def adjust(current: int, delta: int) -> int:
    return max(0, min(100, current + delta))

def state(value: int) -> str:
    if value >= 70:
        return "high"
    if value >= 40:
        return "steady"
    return "low"
