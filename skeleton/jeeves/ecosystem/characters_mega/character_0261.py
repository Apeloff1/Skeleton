"""Character mega 0261.
"""
from __future__ import annotations

ID = "character_mega_0261"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 261, "tier": 261 % 5}

def apply(context: str = "") -> dict:
    if not context and 261 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
