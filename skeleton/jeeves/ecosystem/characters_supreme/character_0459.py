"""Character supreme 0459.
"""
from __future__ import annotations

ID = "character_supreme_0459"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 459, "tier": 459 % 5}

def apply(context: str = "") -> dict:
    if not context and 459 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
