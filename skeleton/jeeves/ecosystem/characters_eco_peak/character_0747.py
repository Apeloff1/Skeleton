"""Character eco_peak 0747.
"""
from __future__ import annotations

ID = "character_eco_peak_0747"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 747, "tier": 747 % 5}

def apply(context: str = "") -> dict:
    if not context and 747 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
