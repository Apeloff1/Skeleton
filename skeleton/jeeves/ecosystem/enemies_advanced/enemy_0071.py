"""Enemy advanced 0071.
"""
from __future__ import annotations

ID = "enemy_adv_0071"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 71}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
