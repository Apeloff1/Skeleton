"""Character apex 0323.
"""
from __future__ import annotations

ID = "character_apex_0323"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 323, "tier": 323 % 5}

def apply(context: str = "") -> dict:
    if not context and 323 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
