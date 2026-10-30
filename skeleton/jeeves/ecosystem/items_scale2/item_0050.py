"""Item scale2 0050.
"""
from __future__ import annotations

ID = "item_scale2_0050"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 50}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
