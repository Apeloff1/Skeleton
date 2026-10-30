"""Item advanced 0138.
"""
from __future__ import annotations

ID = "item_adv_0138"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 138}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
