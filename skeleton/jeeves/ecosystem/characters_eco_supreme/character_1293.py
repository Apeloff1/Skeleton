"""Character eco_supreme 1293.
"""
from __future__ import annotations

ID = "character_eco_supreme_1293"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1293, "tier": 1293 % 5}

def apply(context: str = "") -> dict:
    if not context and 1293 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
