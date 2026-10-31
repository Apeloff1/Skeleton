"""Character peak 0358.
"""
from __future__ import annotations

ID = "character_peak_0358"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 358, "tier": 358 % 5}

def apply(context: str = "") -> dict:
    if not context and 358 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
