"""Item supreme 0592.
"""
from __future__ import annotations

ID = "item_supreme_0592"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 592, "tier": 592 % 5}

def apply(context: str = "") -> dict:
    if not context and 592 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
