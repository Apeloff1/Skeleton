"""Item eco_peak 0451.
"""
from __future__ import annotations

ID = "item_eco_peak_0451"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 451, "tier": 451 % 5}

def apply(context: str = "") -> dict:
    if not context and 451 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
