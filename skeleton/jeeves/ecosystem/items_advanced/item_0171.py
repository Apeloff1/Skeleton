"""Item advanced 0171.
"""
from __future__ import annotations

ID = "item_adv_0171"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 171}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
