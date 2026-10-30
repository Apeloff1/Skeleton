"""Item advanced 0134.
"""
from __future__ import annotations

ID = "item_adv_0134"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 134}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
