"""Character eco_peak 0965.
"""
from __future__ import annotations

ID = "character_eco_peak_0965"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 965, "tier": 965 % 5}

def apply(context: str = "") -> dict:
    if not context and 965 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
