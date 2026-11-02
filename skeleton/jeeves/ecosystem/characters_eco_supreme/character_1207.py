"""Character eco_supreme 1207.
"""
from __future__ import annotations

ID = "character_eco_supreme_1207"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1207, "tier": 1207 % 5}

def apply(context: str = "") -> dict:
    if not context and 1207 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
