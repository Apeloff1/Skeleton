"""Character ultimate 0872.
"""
from __future__ import annotations

ID = "character_ultimate_0872"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 872, "tier": 872 % 5}

def apply(context: str = "") -> dict:
    if not context and 872 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
