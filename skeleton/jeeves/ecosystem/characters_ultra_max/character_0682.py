"""Character ultra_max 0682.
"""
from __future__ import annotations

ID = "character_ultra_max_0682"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 682, "tier": 682 % 5}

def apply(context: str = "") -> dict:
    if not context and 682 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
