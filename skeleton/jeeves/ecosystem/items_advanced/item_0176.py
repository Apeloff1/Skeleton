"""Item advanced 0176.
"""
from __future__ import annotations

ID = "item_adv_0176"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 176}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
