"""Character ultimate 0857.
"""
from __future__ import annotations

ID = "character_ultimate_0857"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 857, "tier": 857 % 5}

def apply(context: str = "") -> dict:
    if not context and 857 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
