"""Item scale2 0091.
"""
from __future__ import annotations

ID = "item_scale2_0091"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 91}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
