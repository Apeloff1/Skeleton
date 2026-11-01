"""Character ultimate 0525.
"""
from __future__ import annotations

ID = "character_ultimate_0525"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 525, "tier": 525 % 5}

def apply(context: str = "") -> dict:
    if not context and 525 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
