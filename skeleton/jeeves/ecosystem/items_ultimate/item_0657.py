"""Item ultimate 0657.
"""
from __future__ import annotations

ID = "item_ultimate_0657"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 657, "tier": 657 % 5}

def apply(context: str = "") -> dict:
    if not context and 657 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
