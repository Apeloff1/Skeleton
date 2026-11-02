"""Character eco_peak 0651.
"""
from __future__ import annotations

ID = "character_eco_peak_0651"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 651, "tier": 651 % 5}

def apply(context: str = "") -> dict:
    if not context and 651 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
