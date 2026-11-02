"""Character eco_supreme 0886.
"""
from __future__ import annotations

ID = "character_eco_supreme_0886"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 886, "tier": 886 % 5}

def apply(context: str = "") -> dict:
    if not context and 886 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
