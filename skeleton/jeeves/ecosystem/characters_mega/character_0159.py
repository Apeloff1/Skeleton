"""Character mega 0159.
"""
from __future__ import annotations

ID = "character_mega_0159"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 159, "tier": 159 % 5}

def apply(context: str = "") -> dict:
    if not context and 159 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
