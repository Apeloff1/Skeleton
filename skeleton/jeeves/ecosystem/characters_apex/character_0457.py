"""Character apex 0457.
"""
from __future__ import annotations

ID = "character_apex_0457"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 457, "tier": 457 % 5}

def apply(context: str = "") -> dict:
    if not context and 457 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
