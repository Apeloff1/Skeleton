"""Character eco_peak 0730.
"""
from __future__ import annotations

ID = "character_eco_peak_0730"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 730, "tier": 730 % 5}

def apply(context: str = "") -> dict:
    if not context and 730 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
