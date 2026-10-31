"""Ability 0035.
"""
from __future__ import annotations

ABILITY = "ability_0035"

def cost() -> int:
    return 5 + (35 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (35 % 15)}
