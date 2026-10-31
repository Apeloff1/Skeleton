"""Character peak 0432.
"""
from __future__ import annotations

ID = "character_peak_0432"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 432, "tier": 432 % 5}

def apply(context: str = "") -> dict:
    if not context and 432 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
