"""Enemy 0098.
"""
from __future__ import annotations

ENEMY = "enemy_0098"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 98, "atk": 5 + (98 % 12), "def": 2 + (98 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
