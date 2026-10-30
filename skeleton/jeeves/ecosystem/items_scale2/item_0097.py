"""Item scale2 0097.
"""
from __future__ import annotations

ID = "item_scale2_0097"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 97}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
