"""Item advanced 0156.
"""
from __future__ import annotations

ID = "item_adv_0156"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 156}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
