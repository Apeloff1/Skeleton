"""Enemy 0095.
"""
from __future__ import annotations

ENEMY = "enemy_0095"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 95, "atk": 5 + (95 % 12), "def": 2 + (95 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
