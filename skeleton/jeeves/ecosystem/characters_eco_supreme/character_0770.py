"""Character eco_supreme 0770.
"""
from __future__ import annotations

ID = "character_eco_supreme_0770"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 770, "tier": 770 % 5}

def apply(context: str = "") -> dict:
    if not context and 770 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
