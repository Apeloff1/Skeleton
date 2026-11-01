"""Item supreme 0483.
"""
from __future__ import annotations

ID = "item_supreme_0483"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 483, "tier": 483 % 5}

def apply(context: str = "") -> dict:
    if not context and 483 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
