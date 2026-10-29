"""Enemy 0022.
"""
from __future__ import annotations

ENEMY = "enemy_0022"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 22, "atk": 5 + (22 % 12), "def": 2 + (22 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
