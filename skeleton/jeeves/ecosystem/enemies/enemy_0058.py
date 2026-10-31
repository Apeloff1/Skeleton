"""Enemy 0058.
"""
from __future__ import annotations

ENEMY = "enemy_0058"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 58, "atk": 5 + (58 % 12), "def": 2 + (58 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
