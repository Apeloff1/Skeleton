"""Character eco_supreme 0926.
"""
from __future__ import annotations

ID = "character_eco_supreme_0926"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 926, "tier": 926 % 5}

def apply(context: str = "") -> dict:
    if not context and 926 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
