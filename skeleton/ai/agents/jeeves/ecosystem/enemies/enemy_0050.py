"""Enemy 0050.
"""
from __future__ import annotations

ENEMY = "enemy_0050"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 50, "atk": 5 + (50 % 12), "def": 2 + (50 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
