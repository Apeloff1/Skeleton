"""Room advanced 0132.
"""
from __future__ import annotations

ID = "room_adv_0132"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 132}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
