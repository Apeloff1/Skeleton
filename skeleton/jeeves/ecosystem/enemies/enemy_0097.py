"""Enemy 0097.
"""
from __future__ import annotations

ENEMY = "enemy_0097"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 97, "atk": 5 + (97 % 12), "def": 2 + (97 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
