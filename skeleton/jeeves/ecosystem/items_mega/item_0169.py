"""Item mega 0169.
"""
from __future__ import annotations

ID = "item_mega_0169"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 169, "tier": 169 % 5}

def apply(context: str = "") -> dict:
    if not context and 169 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
