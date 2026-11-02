"""Character eco_supreme 1236.
"""
from __future__ import annotations

ID = "character_eco_supreme_1236"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1236, "tier": 1236 % 5}

def apply(context: str = "") -> dict:
    if not context and 1236 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
