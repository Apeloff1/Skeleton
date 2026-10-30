"""Enemy advanced 0153.
"""
from __future__ import annotations

ID = "enemy_adv_0153"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 153}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
