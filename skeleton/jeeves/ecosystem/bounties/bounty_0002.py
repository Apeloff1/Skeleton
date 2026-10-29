"""Bounty 0002.
"""
from __future__ import annotations

BOUNTY = "bounty_0002"

def post(target: str, gold: int) -> dict:
    if not target or gold < 0:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "bounty": BOUNTY, "target": target, "gold": gold}
