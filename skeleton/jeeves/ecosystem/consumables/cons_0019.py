"""Consumable 0019.
"""
from __future__ import annotations

CONS = "cons_0019"

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "cons": CONS, "target": target, "heal": 15 + (19 % 20)}
