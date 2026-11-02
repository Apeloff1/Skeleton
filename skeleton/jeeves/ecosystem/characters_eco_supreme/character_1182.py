"""Character eco_supreme 1182.
"""
from __future__ import annotations

ID = "character_eco_supreme_1182"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1182, "tier": 1182 % 5}

def apply(context: str = "") -> dict:
    if not context and 1182 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
