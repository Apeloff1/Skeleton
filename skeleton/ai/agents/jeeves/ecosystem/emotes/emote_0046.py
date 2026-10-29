"""Emote 0046.
"""
from __future__ import annotations

EMOTE = "emote_0046"

def play(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "emote": EMOTE, "actor": actor, "duration": 1.5}
