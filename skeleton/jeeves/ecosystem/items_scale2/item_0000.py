"""Item scale2 0000.
"""
from __future__ import annotations

ID = "item_scale2_0000"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 0}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
