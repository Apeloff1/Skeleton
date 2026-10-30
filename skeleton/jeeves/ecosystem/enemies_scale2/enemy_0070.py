"""Enemy scale2 0070.
"""
from __future__ import annotations

ID = "enemy_scale2_0070"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 70}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
