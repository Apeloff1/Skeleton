"""Character eco_peak 0829.
"""
from __future__ import annotations

ID = "character_eco_peak_0829"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 829, "tier": 829 % 5}

def apply(context: str = "") -> dict:
    if not context and 829 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
