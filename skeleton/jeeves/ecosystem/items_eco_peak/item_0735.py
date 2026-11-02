"""Item eco_peak 0735.
"""
from __future__ import annotations

ID = "item_eco_peak_0735"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 735, "tier": 735 % 5}

def apply(context: str = "") -> dict:
    if not context and 735 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
