"""Item mega 0103.
"""
from __future__ import annotations

ID = "item_mega_0103"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 103, "tier": 103 % 5}

def apply(context: str = "") -> dict:
    if not context and 103 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
