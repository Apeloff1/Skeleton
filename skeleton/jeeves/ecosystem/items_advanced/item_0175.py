"""Item advanced 0175.
"""
from __future__ import annotations

ID = "item_adv_0175"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 175}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
