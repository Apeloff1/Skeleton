"""Enemy advanced 0150.
"""
from __future__ import annotations

ID = "enemy_adv_0150"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 150}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
