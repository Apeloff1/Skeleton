"""Item ultra_max 0470.
"""
from __future__ import annotations

ID = "item_ultra_max_0470"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 470, "tier": 470 % 5}

def apply(context: str = "") -> dict:
    if not context and 470 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
