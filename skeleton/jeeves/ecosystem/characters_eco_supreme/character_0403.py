"""Character eco_supreme 0403.
"""
from __future__ import annotations

ID = "character_eco_supreme_0403"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 403, "tier": 403 % 5}

def apply(context: str = "") -> dict:
    if not context and 403 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
