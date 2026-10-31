"""Character ultra 0331.
"""
from __future__ import annotations

ID = "character_ultra_0331"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 331, "tier": 331 % 5}

def apply(context: str = "") -> dict:
    if not context and 331 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
