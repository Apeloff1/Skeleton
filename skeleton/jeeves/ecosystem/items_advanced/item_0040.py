"""Item advanced 0040.
"""
from __future__ import annotations

ID = "item_adv_0040"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 40}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
