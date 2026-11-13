"""Enemy 0119.
"""
from __future__ import annotations

ENEMY = "enemy_0119"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 119, "atk": 5 + (119 % 12), "def": 2 + (119 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
