"""Enemy ultimate 0535.
"""
from __future__ import annotations

ID = "enemy_ultimate_0535"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 535, "tier": 535 % 5}

def apply(context: str = "") -> dict:
    if not context and 535 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
