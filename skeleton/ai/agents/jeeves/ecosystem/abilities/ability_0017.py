"""Ability 0017.
"""
from __future__ import annotations

ABILITY = "ability_0017"

def cost() -> int:
    return 5 + (17 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (17 % 15)}
