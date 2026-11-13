"""Enemy 0063.
"""
from __future__ import annotations

ENEMY = "enemy_0063"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 63, "atk": 5 + (63 % 12), "def": 2 + (63 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
