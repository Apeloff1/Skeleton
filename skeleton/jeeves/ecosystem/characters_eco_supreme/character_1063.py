"""Character eco_supreme 1063.
"""
from __future__ import annotations

ID = "character_eco_supreme_1063"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1063, "tier": 1063 % 5}

def apply(context: str = "") -> dict:
    if not context and 1063 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
