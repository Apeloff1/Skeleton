"""Character eco_supreme 0977.
"""
from __future__ import annotations

ID = "character_eco_supreme_0977"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 977, "tier": 977 % 5}

def apply(context: str = "") -> dict:
    if not context and 977 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
