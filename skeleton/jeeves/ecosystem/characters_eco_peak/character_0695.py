"""Character eco_peak 0695.
"""
from __future__ import annotations

ID = "character_eco_peak_0695"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 695, "tier": 695 % 5}

def apply(context: str = "") -> dict:
    if not context and 695 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
