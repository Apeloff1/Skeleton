"""Item advanced 0111.
"""
from __future__ import annotations

ID = "item_adv_0111"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 111}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
