"""Enemy 0024.
"""
from __future__ import annotations

ENEMY = "enemy_0024"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 24, "atk": 5 + (24 % 12), "def": 2 + (24 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
