"""Enemy 0026.
"""
from __future__ import annotations

ENEMY = "enemy_0026"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 26, "atk": 5 + (26 % 12), "def": 2 + (26 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
