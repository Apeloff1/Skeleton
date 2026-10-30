"""Enemy advanced 0017.
"""
from __future__ import annotations

ID = "enemy_adv_0017"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 17}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
