"""Character eco_supreme 1274.
"""
from __future__ import annotations

ID = "character_eco_supreme_1274"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1274, "tier": 1274 % 5}

def apply(context: str = "") -> dict:
    if not context and 1274 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
