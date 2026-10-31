"""Character peak 0406.
"""
from __future__ import annotations

ID = "character_peak_0406"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 406, "tier": 406 % 5}

def apply(context: str = "") -> dict:
    if not context and 406 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
