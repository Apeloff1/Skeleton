"""Difficulty: nightmare.
"""
from __future__ import annotations

NAME = "nightmare"
MULTIPLIER = 2.0

def scale_hp(base: int) -> int:
    return max(1, int(base * MULTIPLIER))

def scale_damage(base: int) -> int:
    return max(1, int(base * MULTIPLIER))
