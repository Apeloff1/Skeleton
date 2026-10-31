"""Trap 005.
"""
from __future__ import annotations

TRAP = "trap_005"

def trigger(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "trap": TRAP, "target": target, "damage": 5 + (5 % 10)}
