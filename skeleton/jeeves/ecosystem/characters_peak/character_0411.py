"""Character peak 0411.
"""
from __future__ import annotations

ID = "character_peak_0411"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 411, "tier": 411 % 5}

def apply(context: str = "") -> dict:
    if not context and 411 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
