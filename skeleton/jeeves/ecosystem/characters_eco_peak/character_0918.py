"""Character eco_peak 0918.
"""
from __future__ import annotations

ID = "character_eco_peak_0918"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 918, "tier": 918 % 5}

def apply(context: str = "") -> dict:
    if not context and 918 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
