"""Character ultimate 0885.
"""
from __future__ import annotations

ID = "character_ultimate_0885"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 885, "tier": 885 % 5}

def apply(context: str = "") -> dict:
    if not context and 885 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
