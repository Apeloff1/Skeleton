"""Character peak 0447.
"""
from __future__ import annotations

ID = "character_peak_0447"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 447, "tier": 447 % 5}

def apply(context: str = "") -> dict:
    if not context and 447 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
