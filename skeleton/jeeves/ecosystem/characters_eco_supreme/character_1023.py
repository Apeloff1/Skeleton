"""Character eco_supreme 1023.
"""
from __future__ import annotations

ID = "character_eco_supreme_1023"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1023, "tier": 1023 % 5}

def apply(context: str = "") -> dict:
    if not context and 1023 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
