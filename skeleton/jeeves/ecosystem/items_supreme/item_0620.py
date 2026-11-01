"""Item supreme 0620.
"""
from __future__ import annotations

ID = "item_supreme_0620"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 620, "tier": 620 % 5}

def apply(context: str = "") -> dict:
    if not context and 620 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
