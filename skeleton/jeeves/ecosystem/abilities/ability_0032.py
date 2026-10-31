"""Ability 0032.
"""
from __future__ import annotations

ABILITY = "ability_0032"

def cost() -> int:
    return 5 + (32 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (32 % 15)}
