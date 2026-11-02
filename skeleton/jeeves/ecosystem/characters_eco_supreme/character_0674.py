"""Character eco_supreme 0674.
"""
from __future__ import annotations

ID = "character_eco_supreme_0674"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 674, "tier": 674 % 5}

def apply(context: str = "") -> dict:
    if not context and 674 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
