"""Enemy 0109.
"""
from __future__ import annotations

ENEMY = "enemy_0109"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 109, "atk": 5 + (109 % 12), "def": 2 + (109 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
