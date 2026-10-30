"""Item scale2 0146.
"""
from __future__ import annotations

ID = "item_scale2_0146"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 146}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
