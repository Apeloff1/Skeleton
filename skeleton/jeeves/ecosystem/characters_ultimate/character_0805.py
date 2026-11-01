"""Character ultimate 0805.
"""
from __future__ import annotations

ID = "character_ultimate_0805"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 805, "tier": 805 % 5}

def apply(context: str = "") -> dict:
    if not context and 805 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
