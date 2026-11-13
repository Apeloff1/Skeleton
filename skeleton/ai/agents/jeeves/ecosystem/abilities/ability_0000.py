"""Ability 0000.
"""
from __future__ import annotations

ABILITY = "ability_0000"

def cost() -> int:
    return 5 + (0 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (0 % 15)}
