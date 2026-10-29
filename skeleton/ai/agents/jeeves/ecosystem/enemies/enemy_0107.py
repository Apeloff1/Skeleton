"""Enemy 0107.
"""
from __future__ import annotations

ENEMY = "enemy_0107"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 107, "atk": 5 + (107 % 12), "def": 2 + (107 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
