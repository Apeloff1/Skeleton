"""Character ultra_max 0657.
"""
from __future__ import annotations

ID = "character_ultra_max_0657"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 657, "tier": 657 % 5}

def apply(context: str = "") -> dict:
    if not context and 657 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
