"""Character eco_supreme 0720.
"""
from __future__ import annotations

ID = "character_eco_supreme_0720"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 720, "tier": 720 % 5}

def apply(context: str = "") -> dict:
    if not context and 720 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
