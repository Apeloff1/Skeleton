"""Item eco_supreme 1286.
"""
from __future__ import annotations

ID = "item_eco_supreme_1286"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1286, "tier": 1286 % 5}

def apply(context: str = "") -> dict:
    if not context and 1286 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
