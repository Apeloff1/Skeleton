"""Character supreme 0563.
"""
from __future__ import annotations

ID = "character_supreme_0563"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 563, "tier": 563 % 5}

def apply(context: str = "") -> dict:
    if not context and 563 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
