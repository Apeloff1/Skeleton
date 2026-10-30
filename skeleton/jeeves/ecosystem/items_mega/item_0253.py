"""Item mega 0253.
"""
from __future__ import annotations

ID = "item_mega_0253"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 253, "tier": 253 % 5}

def apply(context: str = "") -> dict:
    if not context and 253 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
