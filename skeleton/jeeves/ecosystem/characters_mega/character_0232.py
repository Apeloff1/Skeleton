"""Character mega 0232.
"""
from __future__ import annotations

ID = "character_mega_0232"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 232, "tier": 232 % 5}

def apply(context: str = "") -> dict:
    if not context and 232 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
