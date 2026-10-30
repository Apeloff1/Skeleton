"""Item advanced 0142.
"""
from __future__ import annotations

ID = "item_adv_0142"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 142}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
