"""Item ultra_max 0616.
"""
from __future__ import annotations

ID = "item_ultra_max_0616"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 616, "tier": 616 % 5}

def apply(context: str = "") -> dict:
    if not context and 616 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
