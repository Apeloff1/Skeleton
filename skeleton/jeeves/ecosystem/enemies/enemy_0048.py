"""Enemy 0048.
"""
from __future__ import annotations

ENEMY = "enemy_0048"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 48, "atk": 5 + (48 % 12), "def": 2 + (48 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
