"""Item supreme 0363.
"""
from __future__ import annotations

ID = "item_supreme_0363"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 363, "tier": 363 % 5}

def apply(context: str = "") -> dict:
    if not context and 363 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
