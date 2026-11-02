"""Character eco_peak 0750.
"""
from __future__ import annotations

ID = "character_eco_peak_0750"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 750, "tier": 750 % 5}

def apply(context: str = "") -> dict:
    if not context and 750 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
