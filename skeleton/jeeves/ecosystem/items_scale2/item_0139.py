"""Item scale2 0139.
"""
from __future__ import annotations

ID = "item_scale2_0139"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 139}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
