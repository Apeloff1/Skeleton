"""Enemy scale2 0046.
"""
from __future__ import annotations

ID = "enemy_scale2_0046"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 46}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
