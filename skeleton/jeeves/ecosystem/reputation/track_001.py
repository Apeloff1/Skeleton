"""Reputation track 001.
"""
from __future__ import annotations

TRACK = "rep_001"

def adjust(current: int, delta: int) -> int:
    return max(-100, min(100, current + delta))

def tier(value: int) -> str:
    if value >= 50:
        return "honored"
    if value >= 0:
        return "neutral"
    return "hostile"
