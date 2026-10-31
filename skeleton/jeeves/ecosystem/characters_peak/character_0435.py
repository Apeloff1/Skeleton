"""Character peak 0435.
"""
from __future__ import annotations

ID = "character_peak_0435"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 435, "tier": 435 % 5}

def apply(context: str = "") -> dict:
    if not context and 435 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
