"""Enemy 0089.
"""
from __future__ import annotations

ENEMY = "enemy_0089"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 89, "atk": 5 + (89 % 12), "def": 2 + (89 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
