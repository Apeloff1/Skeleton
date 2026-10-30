"""Room advanced 0135.
"""
from __future__ import annotations

ID = "room_adv_0135"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 135}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
