"""Character eco_peak 0969.
"""
from __future__ import annotations

ID = "character_eco_peak_0969"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 969, "tier": 969 % 5}

def apply(context: str = "") -> dict:
    if not context and 969 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
