"""Item advanced 0193.
"""
from __future__ import annotations

ID = "item_adv_0193"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 193}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
