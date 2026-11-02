"""Character eco_peak 0927.
"""
from __future__ import annotations

ID = "character_eco_peak_0927"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 927, "tier": 927 % 5}

def apply(context: str = "") -> dict:
    if not context and 927 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
