"""Character eco_supreme 1055.
"""
from __future__ import annotations

ID = "character_eco_supreme_1055"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1055, "tier": 1055 % 5}

def apply(context: str = "") -> dict:
    if not context and 1055 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
