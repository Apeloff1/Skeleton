"""Enemy 0073.
"""
from __future__ import annotations

ENEMY = "enemy_0073"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 73, "atk": 5 + (73 % 12), "def": 2 + (73 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
