"""Item mega 0240.
"""
from __future__ import annotations

ID = "item_mega_0240"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 240, "tier": 240 % 5}

def apply(context: str = "") -> dict:
    if not context and 240 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
