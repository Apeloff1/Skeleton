"""Quest advanced 0105.
"""
from __future__ import annotations

ID = "quest_adv_0105"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 105}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
