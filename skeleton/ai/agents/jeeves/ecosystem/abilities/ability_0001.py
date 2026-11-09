"""Ability 0001.
"""
from __future__ import annotations

ABILITY = "ability_0001"

def cost() -> int:
    return 5 + (1 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (1 % 15)}
