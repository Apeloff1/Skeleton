"""Item ultra_max 0685.
"""
from __future__ import annotations

ID = "item_ultra_max_0685"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 685, "tier": 685 % 5}

def apply(context: str = "") -> dict:
    if not context and 685 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
