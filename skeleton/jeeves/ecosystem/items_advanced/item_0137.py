"""Item advanced 0137.
"""
from __future__ import annotations

ID = "item_adv_0137"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 137}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
