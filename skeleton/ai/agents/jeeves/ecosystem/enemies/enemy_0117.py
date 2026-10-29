"""Enemy 0117.
"""
from __future__ import annotations

ENEMY = "enemy_0117"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 117, "atk": 5 + (117 % 12), "def": 2 + (117 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
