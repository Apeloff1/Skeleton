"""Enemy 0105.
"""
from __future__ import annotations

ENEMY = "enemy_0105"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 105, "atk": 5 + (105 % 12), "def": 2 + (105 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
