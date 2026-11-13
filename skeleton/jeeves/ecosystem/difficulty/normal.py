"""Difficulty: normal.
"""
from __future__ import annotations

NAME = "normal"
MULTIPLIER = 1.0

def scale_hp(base: int) -> int:
    return max(1, int(base * MULTIPLIER))

def scale_damage(base: int) -> int:
    return max(1, int(base * MULTIPLIER))
