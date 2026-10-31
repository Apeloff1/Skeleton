"""Character ultra 0104.
"""
from __future__ import annotations

ID = "character_ultra_0104"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 104, "tier": 104 % 5}

def apply(context: str = "") -> dict:
    if not context and 104 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
