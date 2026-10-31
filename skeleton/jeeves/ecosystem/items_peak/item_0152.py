"""Item peak 0152.
"""
from __future__ import annotations

ID = "item_peak_0152"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 152, "tier": 152 % 5}

def apply(context: str = "") -> dict:
    if not context and 152 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
