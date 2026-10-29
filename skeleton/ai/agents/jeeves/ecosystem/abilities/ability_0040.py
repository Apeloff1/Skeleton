"""Ability 0040.
"""
from __future__ import annotations

ABILITY = "ability_0040"

def cost() -> int:
    return 5 + (40 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (40 % 15)}
