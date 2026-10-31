"""Enemy 0103.
"""
from __future__ import annotations

ENEMY = "enemy_0103"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 103, "atk": 5 + (103 % 12), "def": 2 + (103 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
