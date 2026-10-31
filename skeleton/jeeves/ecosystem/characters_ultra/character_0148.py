"""Character ultra 0148.
"""
from __future__ import annotations

ID = "character_ultra_0148"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 148, "tier": 148 % 5}

def apply(context: str = "") -> dict:
    if not context and 148 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
