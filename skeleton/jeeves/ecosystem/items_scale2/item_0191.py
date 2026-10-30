"""Item scale2 0191.
"""
from __future__ import annotations

ID = "item_scale2_0191"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 191}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
