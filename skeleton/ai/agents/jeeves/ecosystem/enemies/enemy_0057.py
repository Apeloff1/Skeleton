"""Enemy 0057.
"""
from __future__ import annotations

ENEMY = "enemy_0057"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 57, "atk": 5 + (57 % 12), "def": 2 + (57 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
