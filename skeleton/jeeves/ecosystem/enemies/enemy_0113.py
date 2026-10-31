"""Enemy 0113.
"""
from __future__ import annotations

ENEMY = "enemy_0113"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 113, "atk": 5 + (113 % 12), "def": 2 + (113 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
