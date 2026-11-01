"""Item supreme 0796.
"""
from __future__ import annotations

ID = "item_supreme_0796"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 796, "tier": 796 % 5}

def apply(context: str = "") -> dict:
    if not context and 796 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
