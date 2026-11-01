"""Item supreme 0589.
"""
from __future__ import annotations

ID = "item_supreme_0589"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 589, "tier": 589 % 5}

def apply(context: str = "") -> dict:
    if not context and 589 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
