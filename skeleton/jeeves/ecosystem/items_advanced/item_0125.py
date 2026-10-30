"""Item advanced 0125.
"""
from __future__ import annotations

ID = "item_adv_0125"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 125}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
