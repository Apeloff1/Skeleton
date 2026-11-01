"""Character supreme 0479.
"""
from __future__ import annotations

ID = "character_supreme_0479"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 479, "tier": 479 % 5}

def apply(context: str = "") -> dict:
    if not context and 479 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
