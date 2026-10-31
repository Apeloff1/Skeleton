"""Enemy 0092.
"""
from __future__ import annotations

ENEMY = "enemy_0092"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 92, "atk": 5 + (92 % 12), "def": 2 + (92 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
