"""Character eco_peak 0954.
"""
from __future__ import annotations

ID = "character_eco_peak_0954"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 954, "tier": 954 % 5}

def apply(context: str = "") -> dict:
    if not context and 954 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
