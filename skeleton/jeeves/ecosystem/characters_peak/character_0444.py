"""Character peak 0444.
"""
from __future__ import annotations

ID = "character_peak_0444"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 444, "tier": 444 % 5}

def apply(context: str = "") -> dict:
    if not context and 444 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
