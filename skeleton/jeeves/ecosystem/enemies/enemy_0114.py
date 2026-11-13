"""Enemy 0114.
"""
from __future__ import annotations

ENEMY = "enemy_0114"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 114, "atk": 5 + (114 % 12), "def": 2 + (114 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
