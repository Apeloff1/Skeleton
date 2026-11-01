"""Character supreme 0612.
"""
from __future__ import annotations

ID = "character_supreme_0612"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 612, "tier": 612 % 5}

def apply(context: str = "") -> dict:
    if not context and 612 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
