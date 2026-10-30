"""Character scale 0126.
"""
from __future__ import annotations

ID = "character_scale_0126"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 126, "tier": 126 % 5}

def apply(context: str = "") -> dict:
    if not context and 126 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
