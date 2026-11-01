"""Item ultra_max 0667.
"""
from __future__ import annotations

ID = "item_ultra_max_0667"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 667, "tier": 667 % 5}

def apply(context: str = "") -> dict:
    if not context and 667 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
