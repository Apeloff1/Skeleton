"""Item scale2 0083.
"""
from __future__ import annotations

ID = "item_scale2_0083"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 83}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
