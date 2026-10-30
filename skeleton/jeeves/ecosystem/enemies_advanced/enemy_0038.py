"""Enemy advanced 0038.
"""
from __future__ import annotations

ID = "enemy_adv_0038"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 38}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
