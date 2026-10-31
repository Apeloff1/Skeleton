"""Character ultra 0186.
"""
from __future__ import annotations

ID = "character_ultra_0186"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 186, "tier": 186 % 5}

def apply(context: str = "") -> dict:
    if not context and 186 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
