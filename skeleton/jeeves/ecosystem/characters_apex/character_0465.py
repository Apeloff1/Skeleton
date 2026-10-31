"""Character apex 0465.
"""
from __future__ import annotations

ID = "character_apex_0465"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 465, "tier": 465 % 5}

def apply(context: str = "") -> dict:
    if not context and 465 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
