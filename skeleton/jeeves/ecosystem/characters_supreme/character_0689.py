"""Character supreme 0689.
"""
from __future__ import annotations

ID = "character_supreme_0689"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 689, "tier": 689 % 5}

def apply(context: str = "") -> dict:
    if not context and 689 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
