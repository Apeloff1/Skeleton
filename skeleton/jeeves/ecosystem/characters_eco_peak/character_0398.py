"""Character eco_peak 0398.
"""
from __future__ import annotations

ID = "character_eco_peak_0398"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 398, "tier": 398 % 5}

def apply(context: str = "") -> dict:
    if not context and 398 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
