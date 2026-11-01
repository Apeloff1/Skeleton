"""Item supreme 0742.
"""
from __future__ import annotations

ID = "item_supreme_0742"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 742, "tier": 742 % 5}

def apply(context: str = "") -> dict:
    if not context and 742 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
