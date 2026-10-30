"""Character mega 0273.
"""
from __future__ import annotations

ID = "character_mega_0273"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 273, "tier": 273 % 5}

def apply(context: str = "") -> dict:
    if not context and 273 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
