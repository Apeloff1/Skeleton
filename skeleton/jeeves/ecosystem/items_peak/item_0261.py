"""Item peak 0261.
"""
from __future__ import annotations

ID = "item_peak_0261"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 261, "tier": 261 % 5}

def apply(context: str = "") -> dict:
    if not context and 261 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
