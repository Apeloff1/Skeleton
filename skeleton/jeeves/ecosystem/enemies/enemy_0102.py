"""Enemy 0102.
"""
from __future__ import annotations

ENEMY = "enemy_0102"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 102, "atk": 5 + (102 % 12), "def": 2 + (102 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
