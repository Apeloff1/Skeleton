"""Item eco_supreme 0874.
"""
from __future__ import annotations

ID = "item_eco_supreme_0874"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 874, "tier": 874 % 5}

def apply(context: str = "") -> dict:
    if not context and 874 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
