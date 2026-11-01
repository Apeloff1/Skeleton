"""Character ultimate 0888.
"""
from __future__ import annotations

ID = "character_ultimate_0888"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 888, "tier": 888 % 5}

def apply(context: str = "") -> dict:
    if not context and 888 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
