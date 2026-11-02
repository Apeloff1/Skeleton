"""Character eco_peak 0567.
"""
from __future__ import annotations

ID = "character_eco_peak_0567"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 567, "tier": 567 % 5}

def apply(context: str = "") -> dict:
    if not context and 567 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
