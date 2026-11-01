"""Character ultimate 0843.
"""
from __future__ import annotations

ID = "character_ultimate_0843"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 843, "tier": 843 % 5}

def apply(context: str = "") -> dict:
    if not context and 843 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
