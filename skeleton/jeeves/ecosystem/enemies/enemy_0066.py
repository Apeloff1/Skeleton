"""Enemy 0066.
"""
from __future__ import annotations

ENEMY = "enemy_0066"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 66, "atk": 5 + (66 % 12), "def": 2 + (66 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
