"""Character peak 0429.
"""
from __future__ import annotations

ID = "character_peak_0429"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 429, "tier": 429 % 5}

def apply(context: str = "") -> dict:
    if not context and 429 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
