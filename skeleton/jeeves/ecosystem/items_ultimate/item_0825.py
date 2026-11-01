"""Item ultimate 0825.
"""
from __future__ import annotations

ID = "item_ultimate_0825"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 825, "tier": 825 % 5}

def apply(context: str = "") -> dict:
    if not context and 825 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
