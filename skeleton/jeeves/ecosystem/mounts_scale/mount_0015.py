"""Mount advanced 0015.
"""
from __future__ import annotations

ID = "mount_adv_0015"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "value": 10 + 15}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
