"""Enemy advanced 0102.
"""
from __future__ import annotations

ID = "enemy_adv_0102"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 102}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
