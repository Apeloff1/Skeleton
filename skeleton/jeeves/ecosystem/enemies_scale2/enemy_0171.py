"""Enemy scale2 0171.
"""
from __future__ import annotations

ID = "enemy_scale2_0171"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 171}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
