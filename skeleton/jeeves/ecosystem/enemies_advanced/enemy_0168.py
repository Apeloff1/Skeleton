"""Enemy advanced 0168.
"""
from __future__ import annotations

ID = "enemy_adv_0168"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 168}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
