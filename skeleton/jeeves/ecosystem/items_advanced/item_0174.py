"""Item advanced 0174.
"""
from __future__ import annotations

ID = "item_adv_0174"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 174}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
