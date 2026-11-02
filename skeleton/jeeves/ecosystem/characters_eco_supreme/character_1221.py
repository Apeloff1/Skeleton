"""Character eco_supreme 1221.
"""
from __future__ import annotations

ID = "character_eco_supreme_1221"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1221, "tier": 1221 % 5}

def apply(context: str = "") -> dict:
    if not context and 1221 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
