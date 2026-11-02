"""Character eco_peak 0461.
"""
from __future__ import annotations

ID = "character_eco_peak_0461"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 461, "tier": 461 % 5}

def apply(context: str = "") -> dict:
    if not context and 461 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
