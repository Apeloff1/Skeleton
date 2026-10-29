"""Enemy 0042.
"""
from __future__ import annotations

ENEMY = "enemy_0042"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 42, "atk": 5 + (42 % 12), "def": 2 + (42 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
