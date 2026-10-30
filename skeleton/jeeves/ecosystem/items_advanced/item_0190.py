"""Item advanced 0190.
"""
from __future__ import annotations

ID = "item_adv_0190"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 190}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
