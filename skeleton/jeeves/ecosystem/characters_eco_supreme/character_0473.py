"""Character eco_supreme 0473.
"""
from __future__ import annotations

ID = "character_eco_supreme_0473"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 473, "tier": 473 % 5}

def apply(context: str = "") -> dict:
    if not context and 473 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
