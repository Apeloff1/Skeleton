"""Character eco_supreme 0711.
"""
from __future__ import annotations

ID = "character_eco_supreme_0711"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 711, "tier": 711 % 5}

def apply(context: str = "") -> dict:
    if not context and 711 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
