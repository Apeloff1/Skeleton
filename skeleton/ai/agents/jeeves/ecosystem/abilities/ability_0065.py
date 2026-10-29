"""Ability 0065.
"""
from __future__ import annotations

ABILITY = "ability_0065"

def cost() -> int:
    return 5 + (65 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (65 % 15)}
