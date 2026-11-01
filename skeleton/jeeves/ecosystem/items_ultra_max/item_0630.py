"""Item ultra_max 0630.
"""
from __future__ import annotations

ID = "item_ultra_max_0630"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 630, "tier": 630 % 5}

def apply(context: str = "") -> dict:
    if not context and 630 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
