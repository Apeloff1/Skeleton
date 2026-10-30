"""Item mega 0115.
"""
from __future__ import annotations

ID = "item_mega_0115"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 115, "tier": 115 % 5}

def apply(context: str = "") -> dict:
    if not context and 115 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
