"""Enemy 0104.
"""
from __future__ import annotations

ENEMY = "enemy_0104"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 104, "atk": 5 + (104 % 12), "def": 2 + (104 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
