"""Ability 0130.
"""
from __future__ import annotations

ABILITY = "ability_0130"

def cost() -> int:
    return 5 + (130 % 20)

def apply(caster: str, target: str) -> dict:
    if not caster or not target:
        return {"ok": False, "reason": "missing_actor"}
    return {"ok": True, "ability": ABILITY, "caster": caster, "target": target, "power": 10 + (130 % 15)}
