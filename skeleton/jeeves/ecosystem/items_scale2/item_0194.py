"""Item scale2 0194.
"""
from __future__ import annotations

ID = "item_scale2_0194"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 194}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
