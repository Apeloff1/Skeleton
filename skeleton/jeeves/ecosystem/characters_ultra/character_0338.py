"""Character ultra 0338.
"""
from __future__ import annotations

ID = "character_ultra_0338"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 338, "tier": 338 % 5}

def apply(context: str = "") -> dict:
    if not context and 338 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
