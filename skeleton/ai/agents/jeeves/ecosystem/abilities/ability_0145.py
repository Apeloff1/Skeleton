"""Ability 0145.
"""
from __future__ import annotations

ABILITY = "ability_0145"

def cost() -> int:
    return 5 + (145 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (145 % 15)}
