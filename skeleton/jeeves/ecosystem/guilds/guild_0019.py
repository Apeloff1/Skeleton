"""Guild 0019.
"""
from __future__ import annotations

GUILD = "guild_0019"

def join(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "guild": GUILD, "player": player, "rank": "recruit"}
