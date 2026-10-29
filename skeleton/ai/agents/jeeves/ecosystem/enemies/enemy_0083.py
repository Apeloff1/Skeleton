"""Enemy 0083.
"""
from __future__ import annotations

ENEMY = "enemy_0083"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 83, "atk": 5 + (83 % 12), "def": 2 + (83 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
