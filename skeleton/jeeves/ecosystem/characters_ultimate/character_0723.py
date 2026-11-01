"""Character ultimate 0723.
"""
from __future__ import annotations

ID = "character_ultimate_0723"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 723, "tier": 723 % 5}

def apply(context: str = "") -> dict:
    if not context and 723 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
