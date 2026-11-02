"""Character eco_peak 0635.
"""
from __future__ import annotations

ID = "character_eco_peak_0635"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 635, "tier": 635 % 5}

def apply(context: str = "") -> dict:
    if not context and 635 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
