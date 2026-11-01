"""Character ultimate 0892.
"""
from __future__ import annotations

ID = "character_ultimate_0892"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 892, "tier": 892 % 5}

def apply(context: str = "") -> dict:
    if not context and 892 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
