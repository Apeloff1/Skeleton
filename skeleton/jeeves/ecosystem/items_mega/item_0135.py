"""Item mega 0135.
"""
from __future__ import annotations

ID = "item_mega_0135"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 135, "tier": 135 % 5}

def apply(context: str = "") -> dict:
    if not context and 135 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
