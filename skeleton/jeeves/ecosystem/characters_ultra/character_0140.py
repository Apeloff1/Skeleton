"""Character ultra 0140.
"""
from __future__ import annotations

ID = "character_ultra_0140"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 140, "tier": 140 % 5}

def apply(context: str = "") -> dict:
    if not context and 140 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
