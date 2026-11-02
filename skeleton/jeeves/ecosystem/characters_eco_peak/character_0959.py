"""Character eco_peak 0959.
"""
from __future__ import annotations

ID = "character_eco_peak_0959"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 959, "tier": 959 % 5}

def apply(context: str = "") -> dict:
    if not context and 959 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
