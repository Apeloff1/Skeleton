"""Character eco_peak 0902.
"""
from __future__ import annotations

ID = "character_eco_peak_0902"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 902, "tier": 902 % 5}

def apply(context: str = "") -> dict:
    if not context and 902 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
