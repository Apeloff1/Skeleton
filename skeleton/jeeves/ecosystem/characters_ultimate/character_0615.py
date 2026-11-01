"""Character ultimate 0615.
"""
from __future__ import annotations

ID = "character_ultimate_0615"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 615, "tier": 615 % 5}

def apply(context: str = "") -> dict:
    if not context and 615 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
