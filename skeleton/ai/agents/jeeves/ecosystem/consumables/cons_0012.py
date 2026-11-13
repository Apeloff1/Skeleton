"""Consumable 0012.
"""
from __future__ import annotations

CONS = "cons_0012"

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "cons": CONS, "target": target, "heal": 15 + (12 % 20)}
