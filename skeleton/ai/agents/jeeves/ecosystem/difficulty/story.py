"""Difficulty: story.
"""
from __future__ import annotations

NAME = "story"
MULTIPLIER = 0.6

def scale_hp(base: int) -> int:
    return max(1, int(base * MULTIPLIER))

def scale_damage(base: int) -> int:
    return max(1, int(base * MULTIPLIER))
