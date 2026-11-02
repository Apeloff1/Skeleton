"""Character eco_supreme 0585.
"""
from __future__ import annotations

ID = "character_eco_supreme_0585"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 585, "tier": 585 % 5}

def apply(context: str = "") -> dict:
    if not context and 585 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
