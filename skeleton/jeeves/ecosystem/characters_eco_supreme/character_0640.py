"""Character eco_supreme 0640.
"""
from __future__ import annotations

ID = "character_eco_supreme_0640"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 640, "tier": 640 % 5}

def apply(context: str = "") -> dict:
    if not context and 640 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
