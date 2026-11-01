"""Character supreme 0426.
"""
from __future__ import annotations

ID = "character_supreme_0426"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 426, "tier": 426 % 5}

def apply(context: str = "") -> dict:
    if not context and 426 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
