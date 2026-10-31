"""Character apex 0407.
"""
from __future__ import annotations

ID = "character_apex_0407"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 407, "tier": 407 % 5}

def apply(context: str = "") -> dict:
    if not context and 407 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
