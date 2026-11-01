"""Character ultimate 0614.
"""
from __future__ import annotations

ID = "character_ultimate_0614"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 614, "tier": 614 % 5}

def apply(context: str = "") -> dict:
    if not context and 614 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
