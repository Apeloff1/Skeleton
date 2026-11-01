"""Character ultimate 0826.
"""
from __future__ import annotations

ID = "character_ultimate_0826"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 826, "tier": 826 % 5}

def apply(context: str = "") -> dict:
    if not context and 826 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
