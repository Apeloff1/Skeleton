"""Character ultimate 0881.
"""
from __future__ import annotations

ID = "character_ultimate_0881"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 881, "tier": 881 % 5}

def apply(context: str = "") -> dict:
    if not context and 881 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
