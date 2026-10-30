"""Quest advanced 0117.
"""
from __future__ import annotations

ID = "quest_adv_0117"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 117}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
