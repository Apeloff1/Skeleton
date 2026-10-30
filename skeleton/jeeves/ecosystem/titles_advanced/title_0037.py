"""Title advanced 0037.
"""
from __future__ import annotations

ID = "title_adv_0037"

def describe() -> dict:
    return {"id": ID, "kind": "title", "value": 10 + 37}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
