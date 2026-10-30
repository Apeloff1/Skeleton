"""Title advanced 0073.
"""
from __future__ import annotations

ID = "title_adv_0073"

def describe() -> dict:
    return {"id": ID, "kind": "title", "value": 10 + 73}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
