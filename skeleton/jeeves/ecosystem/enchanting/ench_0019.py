"""Enchant 0019.
"""
from __future__ import annotations

ENCH = "ench_0019"

def apply(item: str, power: float = 0.8) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "ench": ENCH, "item": item, "bonus": round(power * 0.2, 3)}
