"""Enemy 0118.
"""
from __future__ import annotations

ENEMY = "enemy_0118"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 118, "atk": 5 + (118 % 12), "def": 2 + (118 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
