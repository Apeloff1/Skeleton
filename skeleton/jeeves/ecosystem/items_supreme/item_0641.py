"""Item supreme 0641.
"""
from __future__ import annotations

ID = "item_supreme_0641"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 641, "tier": 641 % 5}

def apply(context: str = "") -> dict:
    if not context and 641 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
