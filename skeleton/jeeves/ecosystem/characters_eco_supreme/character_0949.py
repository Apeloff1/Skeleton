"""Character eco_supreme 0949.
"""
from __future__ import annotations

ID = "character_eco_supreme_0949"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 949, "tier": 949 % 5}

def apply(context: str = "") -> dict:
    if not context and 949 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
