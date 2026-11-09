"""Enemy 0020.
"""
from __future__ import annotations

ENEMY = "enemy_0020"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 20, "atk": 5 + (20 % 12), "def": 2 + (20 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
