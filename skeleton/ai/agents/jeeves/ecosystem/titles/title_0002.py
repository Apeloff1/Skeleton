"""Title 0002.
"""
from __future__ import annotations

TITLE = "title_0002"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "title": TITLE, "player": player}
