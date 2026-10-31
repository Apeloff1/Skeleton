"""Item peak 0362.
"""
from __future__ import annotations

ID = "item_peak_0362"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 362, "tier": 362 % 5}

def apply(context: str = "") -> dict:
    if not context and 362 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
