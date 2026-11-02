"""Character eco_supreme 0838.
"""
from __future__ import annotations

ID = "character_eco_supreme_0838"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 838, "tier": 838 % 5}

def apply(context: str = "") -> dict:
    if not context and 838 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
