"""Enemy advanced 0130.
"""
from __future__ import annotations

ID = "enemy_adv_0130"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 130}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
