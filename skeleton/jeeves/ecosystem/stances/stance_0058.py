"""Stance 0058.
"""
from __future__ import annotations

STANCE = "stance_0058"

def enter(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "stance": STANCE, "actor": actor, "bonus": "atk" if 58 % 2 == 0 else "def"}
