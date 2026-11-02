"""Character eco_supreme 0913.
"""
from __future__ import annotations

ID = "character_eco_supreme_0913"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 913, "tier": 913 % 5}

def apply(context: str = "") -> dict:
    if not context and 913 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
