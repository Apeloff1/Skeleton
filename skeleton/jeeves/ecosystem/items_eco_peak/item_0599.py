"""Item eco_peak 0599.
"""
from __future__ import annotations

ID = "item_eco_peak_0599"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 599, "tier": 599 % 5}

def apply(context: str = "") -> dict:
    if not context and 599 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
