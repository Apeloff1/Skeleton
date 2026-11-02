"""Character eco_supreme 1218.
"""
from __future__ import annotations

ID = "character_eco_supreme_1218"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1218, "tier": 1218 % 5}

def apply(context: str = "") -> dict:
    if not context and 1218 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
