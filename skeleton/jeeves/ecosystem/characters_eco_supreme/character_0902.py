"""Character eco_supreme 0902.
"""
from __future__ import annotations

ID = "character_eco_supreme_0902"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 902, "tier": 902 % 5}

def apply(context: str = "") -> dict:
    if not context and 902 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
