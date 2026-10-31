"""Item peak 0417.
"""
from __future__ import annotations

ID = "item_peak_0417"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 417, "tier": 417 % 5}

def apply(context: str = "") -> dict:
    if not context and 417 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
