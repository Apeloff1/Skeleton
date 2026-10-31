"""Character ultra 0298.
"""
from __future__ import annotations

ID = "character_ultra_0298"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 298, "tier": 298 % 5}

def apply(context: str = "") -> dict:
    if not context and 298 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
