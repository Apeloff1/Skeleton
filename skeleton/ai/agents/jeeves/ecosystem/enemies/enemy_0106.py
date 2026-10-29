"""Enemy 0106.
"""
from __future__ import annotations

ENEMY = "enemy_0106"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 106, "atk": 5 + (106 % 12), "def": 2 + (106 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
