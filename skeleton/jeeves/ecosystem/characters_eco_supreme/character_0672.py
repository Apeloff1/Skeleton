"""Character eco_supreme 0672.
"""
from __future__ import annotations

ID = "character_eco_supreme_0672"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 672, "tier": 672 % 5}

def apply(context: str = "") -> dict:
    if not context and 672 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
