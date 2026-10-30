"""Item mega 0254.
"""
from __future__ import annotations

ID = "item_mega_0254"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 254, "tier": 254 % 5}

def apply(context: str = "") -> dict:
    if not context and 254 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
