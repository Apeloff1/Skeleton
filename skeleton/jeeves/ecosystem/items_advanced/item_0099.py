"""Item advanced 0099.
"""
from __future__ import annotations

ID = "item_adv_0099"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
