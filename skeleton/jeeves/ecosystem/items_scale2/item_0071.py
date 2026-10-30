"""Item scale2 0071.
"""
from __future__ import annotations

ID = "item_scale2_0071"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 71}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
