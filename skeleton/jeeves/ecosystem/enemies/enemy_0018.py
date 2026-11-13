"""Enemy 0018.
"""
from __future__ import annotations

ENEMY = "enemy_0018"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 18, "atk": 5 + (18 % 12), "def": 2 + (18 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
