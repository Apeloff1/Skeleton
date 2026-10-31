"""Character peak 0420.
"""
from __future__ import annotations

ID = "character_peak_0420"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 420, "tier": 420 % 5}

def apply(context: str = "") -> dict:
    if not context and 420 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
