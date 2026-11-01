"""Character supreme 0595.
"""
from __future__ import annotations

ID = "character_supreme_0595"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 595, "tier": 595 % 5}

def apply(context: str = "") -> dict:
    if not context and 595 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
