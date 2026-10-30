"""Enemy advanced 0036.
"""
from __future__ import annotations

ID = "enemy_adv_0036"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 36}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
