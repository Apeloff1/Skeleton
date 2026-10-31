"""Character peak 0423.
"""
from __future__ import annotations

ID = "character_peak_0423"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 423, "tier": 423 % 5}

def apply(context: str = "") -> dict:
    if not context and 423 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
