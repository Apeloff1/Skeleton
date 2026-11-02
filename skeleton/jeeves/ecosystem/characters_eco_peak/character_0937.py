"""Character eco_peak 0937.
"""
from __future__ import annotations

ID = "character_eco_peak_0937"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 937, "tier": 937 % 5}

def apply(context: str = "") -> dict:
    if not context and 937 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
