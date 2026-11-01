"""Character supreme 0476.
"""
from __future__ import annotations

ID = "character_supreme_0476"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 476, "tier": 476 % 5}

def apply(context: str = "") -> dict:
    if not context and 476 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
