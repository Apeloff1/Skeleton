"""Character mega 0244.
"""
from __future__ import annotations

ID = "character_mega_0244"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 244, "tier": 244 % 5}

def apply(context: str = "") -> dict:
    if not context and 244 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
