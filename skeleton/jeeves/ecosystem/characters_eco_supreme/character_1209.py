"""Character eco_supreme 1209.
"""
from __future__ import annotations

ID = "character_eco_supreme_1209"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1209, "tier": 1209 % 5}

def apply(context: str = "") -> dict:
    if not context and 1209 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
