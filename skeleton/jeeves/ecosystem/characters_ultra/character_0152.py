"""Character ultra 0152.
"""
from __future__ import annotations

ID = "character_ultra_0152"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 152, "tier": 152 % 5}

def apply(context: str = "") -> dict:
    if not context and 152 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
