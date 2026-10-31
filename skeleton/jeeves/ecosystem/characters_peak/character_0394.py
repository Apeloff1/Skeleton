"""Character peak 0394.
"""
from __future__ import annotations

ID = "character_peak_0394"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 394, "tier": 394 % 5}

def apply(context: str = "") -> dict:
    if not context and 394 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
