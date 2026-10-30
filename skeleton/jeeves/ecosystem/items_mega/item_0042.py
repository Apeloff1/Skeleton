"""Item mega 0042.
"""
from __future__ import annotations

ID = "item_mega_0042"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 42, "tier": 42 % 5}

def apply(context: str = "") -> dict:
    if not context and 42 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
