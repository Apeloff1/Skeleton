"""Enemy 0016.
"""
from __future__ import annotations

ENEMY = "enemy_0016"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 16, "atk": 5 + (16 % 12), "def": 2 + (16 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
