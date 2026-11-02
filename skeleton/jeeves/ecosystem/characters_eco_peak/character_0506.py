"""Character eco_peak 0506.
"""
from __future__ import annotations

ID = "character_eco_peak_0506"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 506, "tier": 506 % 5}

def apply(context: str = "") -> dict:
    if not context and 506 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
