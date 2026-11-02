"""Item eco_peak 0838.
"""
from __future__ import annotations

ID = "item_eco_peak_0838"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 838, "tier": 838 % 5}

def apply(context: str = "") -> dict:
    if not context and 838 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
