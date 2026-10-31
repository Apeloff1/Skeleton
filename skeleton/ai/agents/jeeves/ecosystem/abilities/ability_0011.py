"""Ability 0011.
"""
from __future__ import annotations

ABILITY = "ability_0011"

def cost() -> int:
    return 5 + (11 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (11 % 15)}
