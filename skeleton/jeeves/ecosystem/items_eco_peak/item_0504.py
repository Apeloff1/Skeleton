"""Item eco_peak 0504.
"""
from __future__ import annotations

ID = "item_eco_peak_0504"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 504, "tier": 504 % 5}

def apply(context: str = "") -> dict:
    if not context and 504 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
