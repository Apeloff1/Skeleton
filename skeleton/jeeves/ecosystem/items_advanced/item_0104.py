"""Item advanced 0104.
"""
from __future__ import annotations

ID = "item_adv_0104"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 104}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
