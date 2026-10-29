"""Enemy 0002.
"""
from __future__ import annotations

ENEMY = "enemy_0002"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 2, "atk": 5 + (2 % 12), "def": 2 + (2 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
