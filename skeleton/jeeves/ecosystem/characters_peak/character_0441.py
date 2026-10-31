"""Character peak 0441.
"""
from __future__ import annotations

ID = "character_peak_0441"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 441, "tier": 441 % 5}

def apply(context: str = "") -> dict:
    if not context and 441 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
