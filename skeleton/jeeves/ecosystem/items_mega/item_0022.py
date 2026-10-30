"""Item mega 0022.
"""
from __future__ import annotations

ID = "item_mega_0022"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 22, "tier": 22 % 5}

def apply(context: str = "") -> dict:
    if not context and 22 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
