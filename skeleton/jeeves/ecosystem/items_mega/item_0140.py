"""Item mega 0140.
"""
from __future__ import annotations

ID = "item_mega_0140"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 140, "tier": 140 % 5}

def apply(context: str = "") -> dict:
    if not context and 140 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
