"""Character eco_peak 0914.
"""
from __future__ import annotations

ID = "character_eco_peak_0914"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 914, "tier": 914 % 5}

def apply(context: str = "") -> dict:
    if not context and 914 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
