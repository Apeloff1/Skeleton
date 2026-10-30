"""Item mega 0256.
"""
from __future__ import annotations

ID = "item_mega_0256"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 256, "tier": 256 % 5}

def apply(context: str = "") -> dict:
    if not context and 256 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
