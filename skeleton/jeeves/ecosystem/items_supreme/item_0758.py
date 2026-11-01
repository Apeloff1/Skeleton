"""Item supreme 0758.
"""
from __future__ import annotations

ID = "item_supreme_0758"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 758, "tier": 758 % 5}

def apply(context: str = "") -> dict:
    if not context and 758 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
