"""Enemy 0080.
"""
from __future__ import annotations

ENEMY = "enemy_0080"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 80, "atk": 5 + (80 % 12), "def": 2 + (80 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
