"""Difficulty: hard.
"""
from __future__ import annotations

NAME = "hard"
MULTIPLIER = 1.4

def scale_hp(base: int) -> int:
    return max(1, int(base * MULTIPLIER))

def scale_damage(base: int) -> int:
    return max(1, int(base * MULTIPLIER))
