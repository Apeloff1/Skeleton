"""Item scale2 0028.
"""
from __future__ import annotations

ID = "item_scale2_0028"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 28}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
