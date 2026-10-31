"""Bounty 0004.
"""
from __future__ import annotations

BOUNTY = "bounty_0004"

def post(target: str, gold: int) -> dict:
    if not target or gold < 0:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "bounty": BOUNTY, "target": target, "gold": gold}
