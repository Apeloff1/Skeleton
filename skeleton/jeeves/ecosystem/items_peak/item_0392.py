"""Item peak 0392.
"""
from __future__ import annotations

ID = "item_peak_0392"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 392, "tier": 392 % 5}

def apply(context: str = "") -> dict:
    if not context and 392 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
