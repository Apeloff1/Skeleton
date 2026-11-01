"""Character supreme 0681.
"""
from __future__ import annotations

ID = "character_supreme_0681"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 681, "tier": 681 % 5}

def apply(context: str = "") -> dict:
    if not context and 681 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
