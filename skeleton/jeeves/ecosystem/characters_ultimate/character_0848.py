"""Character ultimate 0848.
"""
from __future__ import annotations

ID = "character_ultimate_0848"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 848, "tier": 848 % 5}

def apply(context: str = "") -> dict:
    if not context and 848 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
