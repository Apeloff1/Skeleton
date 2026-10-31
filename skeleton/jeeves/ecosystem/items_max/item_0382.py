"""Item max 0382.
"""
from __future__ import annotations

ID = "item_max_0382"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 382, "tier": 382 % 5}

def apply(context: str = "") -> dict:
    if not context and 382 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
